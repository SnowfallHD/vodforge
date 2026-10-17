// Native single-icon installer. No elevation, automatic quit, telemetry or shell.
#import <AppKit/AppKit.h>
#import <Security/Security.h>
#import <CommonCrypto/CommonDigest.h>
#include <sys/stat.h>
#include <stdio.h>

static NSString *const VFIdentifier = @"com.snowfallhd.vodforge";
static NSString *const VFRequirement = @"anchor apple generic and identifier \"com.snowfallhd.vodforge\" and certificate leaf[subject.OU] = \"76G5W4954G\"";

static NSError *Failure(NSString *message) {
    return [NSError errorWithDomain:@"VODForgeInstaller" code:1
        userInfo:@{NSLocalizedDescriptionKey: message}];
}

static NSString *Digest(NSURL *url) {
    NSInputStream *stream = [NSInputStream inputStreamWithURL:url];
    [stream open];
    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    uint8_t bytes[65536];
    NSInteger n;
    while ((n = [stream read:bytes maxLength:sizeof(bytes)]) > 0)
        CC_SHA256_Update(&context, bytes, (CC_LONG)n);
    [stream close];
    if (n < 0) return nil;
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(hash, &context);
    NSMutableString *result = [NSMutableString string];
    for (NSUInteger i = 0; i < sizeof(hash); i++) [result appendFormat:@"%02x", hash[i]];
    return result;
}

static BOOL RealDirectory(NSURL *url) {
    struct stat info;
    return lstat(url.fileSystemRepresentation, &info) == 0 && S_ISDIR(info.st_mode);
}

static NSString *Snapshot(NSURL *url) {
    struct stat info;
    if (lstat(url.fileSystemRepresentation, &info) != 0) return nil;
    NSString *hash = Digest([url URLByAppendingPathComponent:@"Contents/MacOS/VODForge"]);
    return [NSString stringWithFormat:@"%llu:%llu:%lld:%ld:%@",
        (unsigned long long)info.st_dev, (unsigned long long)info.st_ino,
        (long long)info.st_mtimespec.tv_sec, info.st_mtimespec.tv_nsec, hash ?: @"missing"];
}

static NSDictionary *CheckApp(NSURL *app, NSString *expectedHash, NSError **error) {
    if (!RealDirectory(app)) {
        if (error) *error = Failure(@"The app must be a real directory, not a link.");
        return nil;
    }
    NSDictionary *info = [NSDictionary dictionaryWithContentsOfURL:
        [app URLByAppendingPathComponent:@"Contents/Info.plist"]];
    if (![info[@"CFBundleIdentifier"] isEqual:VFIdentifier] ||
        ![info[@"CFBundleExecutable"] isEqual:@"VODForge"] ||
        ![info[@"CFBundleShortVersionString"] isKindOfClass:NSString.class]) {
        if (error) *error = Failure(@"The app identity or version is invalid.");
        return nil;
    }
    NSURL *exe = [app URLByAppendingPathComponent:@"Contents/MacOS/VODForge"];
    struct stat exeInfo;
    if (lstat(exe.fileSystemRepresentation, &exeInfo) || !S_ISREG(exeInfo.st_mode) ||
        (expectedHash && ![Digest(exe) isEqual:expectedHash])) {
        if (error) *error = Failure(@"The app executable does not match the installer.");
        return nil;
    }
#ifndef VF_INSTALLER_CORE_TEST
    SecStaticCodeRef code = NULL;
    SecRequirementRef requirement = NULL;
    OSStatus status = SecStaticCodeCreateWithPath((__bridge CFURLRef)app,
        kSecCSDefaultFlags, &code);
    if (status == errSecSuccess) status = SecRequirementCreateWithString(
        (__bridge CFStringRef)VFRequirement, kSecCSDefaultFlags, &requirement);
    if (status == errSecSuccess) status = SecStaticCodeCheckValidity(code,
        kSecCSStrictValidate | kSecCSCheckAllArchitectures | kSecCSCheckNestedCode,
        requirement);
    if (requirement) CFRelease(requirement);
    if (code) CFRelease(code);
    if (status != errSecSuccess) {
        if (error) *error = Failure(@"The VODForge signature could not be verified. No app was opened.");
        return nil;
    }
#endif
    return info;
}

#ifdef VF_INSTALLER_CORE_TEST
static BOOL VFTestRunning = NO;
#endif
static BOOL Running(void) {
#ifdef VF_INSTALLER_CORE_TEST
    return VFTestRunning;
#else
    return [NSRunningApplication runningApplicationsWithBundleIdentifier:VFIdentifier].count > 0;
#endif
}

// Atomic, non-overwriting renames preserve any unexpected competing destination.
static BOOL MoveExclusive(NSURL *from, NSURL *to, NSError **error) {
    if (renamex_np(from.fileSystemRepresentation, to.fileSystemRepresentation, RENAME_EXCL) == 0)
        return YES;
    if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
    return NO;
}

static BOOL Install(NSURL *payload, NSURL *destination, NSString *expectedHash,
                    NSString *confirmedSnapshot, NSURL **retainedBackup, NSError **error) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSURL *parent = destination.URLByDeletingLastPathComponent;
    NSDictionary *incoming = CheckApp(payload, expectedHash, error);
    if (!RealDirectory(parent) || ![destination.lastPathComponent isEqual:@"VODForge.app"] ||
        !incoming) return NO;
    NSString *current = Snapshot(destination);
    if ((current || confirmedSnapshot) && ![current isEqual:confirmedSnapshot]) {
        if (error) *error = Failure(@"The destination changed. Cancel and start again.");
        return NO;
    }
    if (current) {
        NSDictionary *previous = CheckApp(destination, nil, error);
        if (!previous) return NO;
        if ([previous[@"CFBundleShortVersionString"] compare:incoming[@"CFBundleShortVersionString"] options:NSNumericSearch] == NSOrderedDescending) {
            if (error) *error = Failure(@"A newer VODForge is already installed. Nothing was replaced.");
            return NO;
        }
    }
    if (Running()) {
        if (error) *error = Failure(@"Quit VODForge yourself before installing. This installer will not close it.");
        return NO;
    }
    NSURL *stage = [parent URLByAppendingPathComponent:
        [NSString stringWithFormat:@".VODForge-install-%@.app", NSUUID.UUID.UUIDString]];
    if (![fm copyItemAtURL:payload toURL:stage error:error]) {
        [fm removeItemAtURL:stage error:nil];
        return NO;
    }
    if (!CheckApp(stage, expectedHash, error) || Running() ||
        ![(Snapshot(destination) ?: @"") isEqual:(confirmedSnapshot ?: @"")]) {
        [fm removeItemAtURL:stage error:nil];
        if (error && !*error) *error = Failure(@"The app or destination changed before installation.");
        return NO;
    }
    NSURL *backup = nil;
    if (confirmedSnapshot) {
        backup = [parent URLByAppendingPathComponent:
            [NSString stringWithFormat:@"VODForge backup %@.app", NSUUID.UUID.UUIDString]];
        if (!MoveExclusive(destination, backup, error)) {
            [fm removeItemAtURL:stage error:nil];
            return NO;
        }
        if (retainedBackup) *retainedBackup = backup;
    }
    if (!MoveExclusive(stage, destination, error)) {
        NSError *rollbackError = nil;
        if (backup && !MoveExclusive(backup, destination, &rollbackError)) {
            if (error) *error = Failure([NSString stringWithFormat:
                @"Installation stopped. Your previous app is preserved at %@. A new item occupied the destination; it was not overwritten.", backup.path]);
        }
        [fm removeItemAtURL:stage error:nil];
        return NO;
    }
    // A post-copy verification failure is reported; neither app nor backup is deleted.
    return CheckApp(destination, expectedHash, error) != nil;
}

#ifndef VF_INSTALLER_CORE_TEST
static NSModalResponse Alert(NSString *title, NSString *body, NSArray<NSString *> *buttons) {
    NSAlert *alert = [NSAlert new];
    alert.messageText = title;
    alert.informativeText = body;
    for (NSString *button in buttons) [alert addButtonWithTitle:button];
    return alert.runModal;
}

@interface VFInstaller : NSObject <NSApplicationDelegate>
@end
@implementation VFInstaller
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp activateIgnoringOtherApps:YES];
    NSURL *payload = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"VODForge.app"];
    NSString *hash = [NSBundle.mainBundle objectForInfoDictionaryKey:@"VFExecutableSHA256"];
    NSError *error = nil;
    NSDictionary *info = CheckApp(payload, hash, &error);
    if (!info || hash.length != 64) {
        Alert(@"Installer verification failed", error.localizedDescription ?: @"The installer is incomplete.", @[@"Close"]);
        [NSApp terminate:nil]; return;
    }
    if (Running()) {
        Alert(@"Quit VODForge before installing", @"Your open app and its work have been left untouched. Quit it yourself, then open this installer again.", @[@"Close"]);
        [NSApp terminate:nil]; return;
    }
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.title = @"Choose where to install VODForge";
    panel.message = @"Choose Applications or another folder you can write to. No administrator access will be requested.";
    panel.prompt = @"Choose Folder";
    panel.canChooseFiles = NO; panel.canChooseDirectories = YES;
    panel.canCreateDirectories = YES; panel.allowsMultipleSelection = NO;
    panel.directoryURL = [NSURL fileURLWithPath:@"/Applications" isDirectory:YES];
    if (panel.runModal != NSModalResponseOK) { [NSApp terminate:nil]; return; }
    NSURL *destination = [panel.URL URLByAppendingPathComponent:@"VODForge.app"];
    if (!RealDirectory(panel.URL) || ![NSFileManager.defaultManager isWritableFileAtPath:panel.URL.path]) {
        Alert(@"Choose a writable folder", @"Nothing was installed. Open the installer again and choose a folder you can write to, such as Applications in your home folder.", @[@"Close"]);
        [NSApp terminate:nil]; return;
    }
    NSString *snapshot = Snapshot(destination);
    NSString *body = [NSString stringWithFormat:@"Install VODForge %@ at %@? Your settings, history and saved media will not be moved or removed.", info[@"CFBundleShortVersionString"], destination.path];
    if (snapshot) {
        NSDictionary *previous = CheckApp(destination, nil, &error);
        if (!previous || [previous[@"CFBundleShortVersionString"] compare:info[@"CFBundleShortVersionString"] options:NSNumericSearch] == NSOrderedDescending) {
            Alert(@"Cannot replace this app", @"The destination contains an unverified or newer app. Nothing was changed. Choose another folder or keep your existing app.", @[@"Close"]);
            [NSApp terminate:nil]; return;
        }
        body = [body stringByAppendingString:@" The previous app will be kept beside it as a named backup."];
    }
    if (Alert(snapshot ? @"Replace VODForge?" : @"Install VODForge?", body,
              @[snapshot ? @"Replace" : @"Install", @"Cancel"]) != NSAlertFirstButtonReturn) {
        [NSApp terminate:nil]; return;
    }
    NSURL *backup = nil;
    if (!Install(payload, destination, hash, snapshot, &backup, &error)) {
        NSString *reason = error.localizedDescription ?: @"Installation did not finish.";
        if (backup && [NSFileManager.defaultManager fileExistsAtPath:backup.path])
            reason = [reason stringByAppendingFormat:@" Your previous app remains at %@.", backup.path];
        Alert(@"Installation stopped", reason, @[@"Close"]);
        [NSApp terminate:nil]; return;
    }
    NSString *complete = [NSString stringWithFormat:@"Installed at %@.%@", destination.path,
        backup ? [NSString stringWithFormat:@" Previous app preserved at %@.", backup.path] : @""];
    if (Alert(@"VODForge is installed", complete, @[@"Open VODForge", @"Done"]) == NSAlertFirstButtonReturn) {
        // User explicitly requests opening; installation alone never launches it.
        NSWorkspaceOpenConfiguration *configuration = [NSWorkspaceOpenConfiguration configuration];
        configuration.createsNewApplicationInstance = NO;
        [NSWorkspace.sharedWorkspace openApplicationAtURL:destination configuration:configuration
            completionHandler:^(NSRunningApplication *app, NSError *launchError) {
            dispatch_async(dispatch_get_main_queue(), ^{
                NSURL *expected = [destination URLByAppendingPathComponent:@"Contents/MacOS/VODForge"];
                if (launchError || ![app.executableURL.URLByResolvingSymlinksInPath.path
                        isEqual:expected.URLByResolvingSymlinksInPath.path]) {
                    Alert(@"VODForge could not be opened", @"The verified app remains installed. Open it from your chosen folder. No running app was closed.", @[@"Close"]);
                }
                // A returned process is only an open request, not rendered-ready proof.
                [NSApp terminate:nil];
            });
        }];
    } else [NSApp terminate:nil];
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        VFInstaller *delegate = [VFInstaller new];
        app.delegate = delegate;
        [app run];
    }
    return 0;
}
#endif
