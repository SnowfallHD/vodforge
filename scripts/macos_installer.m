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
    __block BOOL running = NO;
    void (^read)(void) = ^{
        running = [NSRunningApplication runningApplicationsWithBundleIdentifier:VFIdentifier].count > 0;
    };
    if (NSThread.isMainThread) read();
    else dispatch_sync(dispatch_get_main_queue(), read);
    return running;
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

// All expensive verification/copy work runs serially away from AppKit's thread.
// The completion is always main-thread; no UI is accessed by the worker block.
static void PerformWork(dispatch_queue_t queue, dispatch_block_t work, dispatch_block_t completion) {
    dispatch_async(queue, ^{
        @autoreleasepool {
            work();
            dispatch_async(dispatch_get_main_queue(), completion);
        }
    });
}

#ifndef VF_INSTALLER_CORE_TEST
static NSModalResponse Alert(NSString *title, NSString *body, NSArray<NSString *> *buttons) {
    NSCAssert(NSThread.isMainThread, @"Installer UI must run on the main thread");
    NSAlert *alert = [NSAlert new];
    alert.messageText = title;
    alert.informativeText = body;
    for (NSString *button in buttons) [alert addButtonWithTitle:button];
    return alert.runModal;
}

@interface VFInstaller : NSObject <NSApplicationDelegate, NSWindowDelegate>
@property(nonatomic, strong) NSWindow *progressWindow;
@property(nonatomic, strong) NSTextField *progressTitle;
@property(nonatomic, strong) NSTextField *progressDetail;
@property(nonatomic, strong) NSProgressIndicator *indicator;
@property(nonatomic, strong) dispatch_queue_t worker;
@property(nonatomic) BOOL mutating;
@end

@implementation VFInstaller
- (void)showProgress:(NSString *)title detail:(NSString *)detail {
    NSCAssert(NSThread.isMainThread, @"Installer UI must run on the main thread");
    if (!self.progressWindow) {
        self.progressWindow = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 470, 166)
            styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
            backing:NSBackingStoreBuffered defer:NO];
        self.progressWindow.title = @"Install VODForge";
        self.progressWindow.delegate = self;
        self.progressWindow.releasedWhenClosed = NO;
        self.progressTitle = [NSTextField labelWithString:title];
        self.progressTitle.font = [NSFont boldSystemFontOfSize:17];
        self.progressTitle.frame = NSMakeRect(24, 114, 422, 26);
        self.progressDetail = [NSTextField wrappingLabelWithString:detail];
        self.progressDetail.frame = NSMakeRect(24, 53, 422, 54);
        self.indicator = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(24, 24, 422, 16)];
        self.indicator.style = NSProgressIndicatorStyleBar;
        self.indicator.indeterminate = YES;
        self.indicator.usesThreadedAnimation = YES;
        [self.progressWindow.contentView addSubview:self.progressTitle];
        [self.progressWindow.contentView addSubview:self.progressDetail];
        [self.progressWindow.contentView addSubview:self.indicator];
        [self.progressWindow center];
    }
    self.progressTitle.stringValue = title;
    self.progressDetail.stringValue = detail;
    [[self.progressWindow standardWindowButton:NSWindowCloseButton] setEnabled:!self.mutating];
    [self.indicator startAnimation:nil];
    [self.progressWindow makeKeyAndOrderFront:nil];
    [self.progressWindow displayIfNeeded];
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (!self.mutating) return NSTerminateNow;
    self.progressDetail.stringValue = @"Installation is in progress. Keep this window open while the app is verified and safely placed. Your existing app and data are being protected.";
    [self.progressWindow makeKeyAndOrderFront:nil];
    NSBeep();
    return NSTerminateCancel;
}
- (BOOL)windowShouldClose:(NSWindow *)sender {
    if (self.mutating) return NO;
    [NSApp terminate:nil];
    return NO;
}
- (void)stopWithTitle:(NSString *)title reason:(NSString *)reason {
    self.mutating = NO;
    [self.indicator stopAnimation:nil];
    Alert(title, reason, @[@"Close"]);
    [NSApp terminate:nil];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.worker = dispatch_queue_create("com.snowfallhd.vodforge.installer.verify-install", DISPATCH_QUEUE_SERIAL);
    [NSApp activateIgnoringOtherApps:YES];
    [self showProgress:@"Checking VODForge…" detail:@"Verifying the included app and its signature. This can take a little while. Nothing is being installed yet."];
    NSURL *payload = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"VODForge.app"];
    NSString *hash = [NSBundle.mainBundle objectForInfoDictionaryKey:@"VFExecutableSHA256"];
    __block NSError *error = nil;
    __block NSDictionary *info = nil;
    PerformWork(self.worker, ^{
        if ([hash isKindOfClass:NSString.class] && hash.length == 64)
            info = CheckApp(payload, hash, &error);
    }, ^{
        if (!info) {
            [self stopWithTitle:@"Installer verification failed" reason:error.localizedDescription ?: @"The installer is incomplete."];
            return;
        }
        [self chooseDestinationForPayload:payload hash:hash info:info];
    });
}
- (void)chooseDestinationForPayload:(NSURL *)payload hash:(NSString *)hash info:(NSDictionary *)info {
    if (Running()) {
        [self stopWithTitle:@"Quit VODForge before installing" reason:@"Your open app and its work have been left untouched. Quit it yourself, then open this installer again."];
        return;
    }
    [self.indicator stopAnimation:nil];
    self.progressTitle.stringValue = @"Choose an installation folder";
    self.progressDetail.stringValue = @"The included app is verified. Nothing will be copied until you choose a folder and confirm.";
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.title = @"Choose where to install VODForge";
    panel.message = @"Choose Applications or another folder you can write to. No administrator access will be requested.";
    panel.prompt = @"Choose Folder";
    panel.canChooseFiles = NO; panel.canChooseDirectories = YES;
    panel.canCreateDirectories = YES; panel.allowsMultipleSelection = NO;
    panel.directoryURL = [NSURL fileURLWithPath:@"/Applications" isDirectory:YES];
    if (panel.runModal != NSModalResponseOK) { [NSApp terminate:nil]; return; }
    NSURL *folder = panel.URL;
    NSURL *destination = [folder URLByAppendingPathComponent:@"VODForge.app"];
    [self showProgress:@"Checking the destination…" detail:@"Checking the selected folder and any existing app before asking you to confirm. Nothing has been replaced."];
    __block NSString *snapshot = nil;
    __block NSError *error = nil;
    __block BOOL checked = NO;
    PerformWork(self.worker, ^{
        if (!RealDirectory(folder) || ![NSFileManager.defaultManager isWritableFileAtPath:folder.path]) {
            error = Failure(@"Choose a folder you can write to, such as Applications in your home folder. Nothing was installed.");
            return;
        }
        snapshot = Snapshot(destination);
        if (snapshot) {
            NSDictionary *previous = CheckApp(destination, nil, &error);
            if (!previous || [previous[@"CFBundleShortVersionString"] compare:info[@"CFBundleShortVersionString"] options:NSNumericSearch] == NSOrderedDescending) {
                error = Failure(@"The destination contains an unverified or newer app. Nothing was changed. Choose another folder or keep your existing app.");
                return;
            }
        }
        checked = YES;
    }, ^{
        if (!checked) {
            [self stopWithTitle:@"Cannot use this destination" reason:error.localizedDescription ?: @"Nothing was installed."];
            return;
        }
        if (Running()) {
            [self stopWithTitle:@"Quit VODForge before installing" reason:@"Your open app and its work have been left untouched. Quit it yourself, then open this installer again."];
            return;
        }
        [self.indicator stopAnimation:nil];
        NSString *body = [NSString stringWithFormat:@"Install VODForge %@ at %@? Your settings, history and saved media will not be moved or removed.", info[@"CFBundleShortVersionString"], destination.path];
        if (snapshot) body = [body stringByAppendingString:@" The previous app will be kept beside it as a named backup."];
        if (Alert(snapshot ? @"Replace VODForge?" : @"Install VODForge?", body,
                  @[snapshot ? @"Replace" : @"Install", @"Cancel"]) != NSAlertFirstButtonReturn) {
            [NSApp terminate:nil]; return;
        }
        [self installPayload:payload destination:destination hash:hash snapshot:snapshot];
    });
}
- (void)installPayload:(NSURL *)payload destination:(NSURL *)destination hash:(NSString *)hash snapshot:(NSString *)snapshot {
    self.mutating = YES;
    [self showProgress:@"Installing VODForge…" detail:@"Copying and verifying the app, then safely placing it in your selected folder. Keep this window open until installation finishes."];
    __block NSURL *backup = nil;
    __block NSError *error = nil;
    __block BOOL installed = NO;
    PerformWork(self.worker, ^{
        installed = Install(payload, destination, hash, snapshot, &backup, &error);
    }, ^{
        self.mutating = NO;
        [[self.progressWindow standardWindowButton:NSWindowCloseButton] setEnabled:YES];
        [self.indicator stopAnimation:nil];
        if (!installed) {
            NSString *reason = error.localizedDescription ?: @"Installation did not finish.";
            if (backup && [NSFileManager.defaultManager fileExistsAtPath:backup.path])
                reason = [reason stringByAppendingFormat:@" Your previous app remains at %@.", backup.path];
            [self stopWithTitle:@"Installation stopped" reason:reason];
            return;
        }
        NSString *complete = [NSString stringWithFormat:@"Installed at %@.%@", destination.path,
            backup ? [NSString stringWithFormat:@" Previous app preserved at %@.", backup.path] : @""];
        if (Alert(@"VODForge is installed", complete, @[@"Open VODForge", @"Done"]) != NSAlertFirstButtonReturn) {
            [NSApp terminate:nil]; return;
        }
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
    });
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
