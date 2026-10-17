// Compile-time-only test harness. Not linked into the shipped installer.
#define VF_INSTALLER_CORE_TEST 1
#define VF_INSTALLER_UI_ROUTING_TEST 1
#include "../scripts/macos_installer.m"

static NSURL *Fixture(NSURL *parent, NSString *name, NSString *bytes, NSString *version) {
    NSURL *app = [parent URLByAppendingPathComponent:name];
    [NSFileManager.defaultManager createDirectoryAtURL:[app URLByAppendingPathComponent:@"Contents/MacOS"]
        withIntermediateDirectories:YES attributes:nil error:nil];
    [@{@"CFBundleIdentifier": VFIdentifier, @"CFBundleExecutable": @"VODForge",
       @"CFBundleShortVersionString": version} writeToURL:
        [app URLByAppendingPathComponent:@"Contents/Info.plist"] atomically:YES];
    [bytes writeToURL:[app URLByAppendingPathComponent:@"Contents/MacOS/VODForge"]
        atomically:YES encoding:NSUTF8StringEncoding error:nil];
    return app;
}

// Compile-time harness dependency only; production always uses defaultManager.
@interface VFUnwritableFileManager : NSFileManager
@end
@implementation VFUnwritableFileManager
- (BOOL)isWritableFileAtPath:(NSString *)path { return NO; }
@end

// Exercise the real routine-path method without creating NSApplication,
// windows or panels. The boundary is overridden before any UI is requested.
@interface VFDestinationRoutingProbe : VFInstaller
@property(nonatomic, strong) NSURL *checkedFolder;
@property(nonatomic) NSUInteger fallbackRequests;
@end
@implementation VFDestinationRoutingProbe
- (void)checkFolder:(NSURL *)folder payload:(NSURL *)payload hash:(NSString *)hash info:(NSDictionary *)info {
    self.checkedFolder = folder;
}
- (void)chooseAlternateFolderForPayload:(NSURL *)payload hash:(NSString *)hash info:(NSDictionary *)info {
    self.fallbackRequests += 1;
}
@end

static void Require(BOOL condition, NSString *label) {
    if (!condition) { fprintf(stderr, "FAIL: %s\n", label.UTF8String); exit(1); }
    printf("PASS: %s\n", label.UTF8String);
}

int main(void) {
    @autoreleasepool {
        NSFileManager *fm = NSFileManager.defaultManager;
        dispatch_queue_t worker = dispatch_queue_create("vf.installer.test.serial", DISPATCH_QUEUE_SERIAL);
        dispatch_semaphore_t started = dispatch_semaphore_create(0);
        dispatch_semaphore_t release = dispatch_semaphore_create(0);
        __block BOOL completed = NO;
        __block BOOL ranOnMain = YES;
        __block NSInteger serialOrder = 0;
        PerformWork(worker, ^{
            ranOnMain = NSThread.isMainThread;
            dispatch_semaphore_signal(started);
            // Bound the negative control too: synchronous scheduling must fail
            // the assertion below rather than hanging this source-only harness.
            dispatch_semaphore_wait(release, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC));
            serialOrder = 1;
        }, ^{
            Require(NSThread.isMainThread, @"worker completion returns to main thread");
            completed = YES;
        });
        Require(dispatch_semaphore_wait(started, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC)) == 0 && !completed,
            @"slow worker starts without blocking the caller/main thread");
        Require(!ranOnMain, @"verification work runs off the main thread");
        __block BOOL secondCompleted = NO;
        PerformWork(worker, ^{
            Require(serialOrder == 1, @"work queue serializes operations");
            serialOrder = 2;
        }, ^{ secondCompleted = YES; });
        dispatch_semaphore_signal(release);
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:3];
        while ((!completed || !secondCompleted) && deadline.timeIntervalSinceNow > 0)
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
        Require(completed && secondCompleted && serialOrder == 2,
            @"main thread services completion while worker work is serialized");
        NSURL *root = [NSURL fileURLWithPath:[NSTemporaryDirectory()
            stringByAppendingPathComponent:[@"vf-installer-core-" stringByAppendingString:NSUUID.UUID.UUIDString]]];
        [fm createDirectoryAtURL:root withIntermediateDirectories:YES attributes:nil error:nil];
        NSURL *payload = Fixture(root, @"payload.app", @"new", @"0.2.6");
        NSURL *destination = [root URLByAppendingPathComponent:@"VODForge.app"];
        NSString *hash = Digest([payload URLByAppendingPathComponent:@"Contents/MacOS/VODForge"]);
        NSError *error = nil;
        Require([DefaultInstallationFolder().path isEqual:@"/Applications"],
            @"routine destination is fixed system Applications");
        NSDictionary *incoming = CheckApp(payload, hash, &error);
        VFDestinationRoutingProbe *route = [VFDestinationRoutingProbe new];
        [route chooseDestinationForPayload:payload hash:hash info:incoming];
        Require([route.checkedFolder.path isEqual:@"/Applications"] && route.fallbackRequests == 0,
            @"routine UI owner checks Applications without requesting a folder picker");
        NSString *selectedSnapshot = nil;
        NSURL *selected = CheckDestinationFolder(root, incoming, fm, &selectedSnapshot, &error);
        Require([selected.path isEqual:destination.path] && !selectedSnapshot &&
            ![fm fileExistsAtPath:destination.path], @"automatic fresh destination is selected without mutation");
        NSURL *alternate = [root URLByAppendingPathComponent:@"Alternate Applications"];
        [fm createDirectoryAtURL:alternate withIntermediateDirectories:NO attributes:nil error:nil];
        error = nil;
        selected = CheckDestinationFolder(alternate, incoming, fm, &selectedSnapshot, &error);
        Require([selected.path isEqual:[alternate URLByAppendingPathComponent:@"VODForge.app"].path] &&
            !selectedSnapshot && ![fm fileExistsAtPath:selected.path],
            @"explicit fallback folder uses the same checked destination owner");
        NSURL *folderLink = [root URLByAppendingPathComponent:@"linked-folder"];
        [fm createSymbolicLinkAtURL:folderLink withDestinationURL:alternate error:nil];
        error = nil;
        Require(!CheckDestinationFolder(folderLink, incoming, fm, NULL, &error) && error,
            @"unsafe default or fallback folder refuses before mutation");
        error = nil;
        Require(!CheckDestinationFolder(root, incoming, [VFUnwritableFileManager new], NULL, &error) && error &&
            ![fm fileExistsAtPath:destination.path], @"unwritable destination requires explicit fallback without mutation");
        NSURL *foreign = Fixture(alternate, @"VODForge.app", @"foreign", @"0.2.6");
        [@{@"CFBundleIdentifier": @"invalid.foreign", @"CFBundleExecutable": @"VODForge",
           @"CFBundleShortVersionString": @"0.2.6"} writeToURL:
            [foreign URLByAppendingPathComponent:@"Contents/Info.plist"] atomically:YES];
        NSString *foreignBefore = Snapshot(foreign);
        error = nil;
        Require(!CheckDestinationFolder(alternate, incoming, fm, NULL, &error) && error &&
            [Snapshot(foreign) isEqual:foreignBefore], @"unverified existing destination is preserved and requires fallback");
        Require(!Install(payload, destination, @"wrong", nil, NULL, &error) &&
            ![fm fileExistsAtPath:destination.path], @"wrong payload hash makes no destination");
        VFTestRunning = YES;
        error = nil;
        Require(!Install(payload, destination, hash, nil, NULL, &error) &&
            ![fm fileExistsAtPath:destination.path], @"running-app admission stops installation");
        VFTestRunning = NO;
        error = nil;
        Require(Install(payload, destination, hash, nil, NULL, &error), @"fresh installation");
        Require([Digest([destination URLByAppendingPathComponent:@"Contents/MacOS/VODForge"]) isEqual:hash],
            @"installed bytes match payload");
        NSString *before = Snapshot(destination);
        error = nil;
        selected = CheckDestinationFolder(root, incoming, fm, &selectedSnapshot, &error);
        Require([selected.path isEqual:destination.path] && [selectedSnapshot isEqual:before],
            @"existing verified destination retains snapshot for explicit Replace confirmation");
        error = nil;
        Require(!Install(payload, destination, hash, @"stale", NULL, &error) &&
            [Snapshot(destination) isEqual:before], @"stale destination refuses without mutation");
        NSURL *backup = nil;
        error = nil;
        Require(Install(payload, destination, hash, before, &backup, &error) &&
            [fm fileExistsAtPath:backup.path], @"confirmed same-version replacement retains backup");
        Require([Digest([backup URLByAppendingPathComponent:@"Contents/MacOS/VODForge"]) isEqual:hash],
            @"backup payload unchanged");
        NSURL *occupied = [root URLByAppendingPathComponent:@"occupied"];
        [@"keep" writeToURL:occupied atomically:YES encoding:NSUTF8StringEncoding error:nil];
        error = nil;
        Require(!MoveExclusive(backup, occupied, &error) && [fm fileExistsAtPath:backup.path] &&
            [[NSString stringWithContentsOfURL:occupied encoding:NSUTF8StringEncoding error:nil] isEqual:@"keep"],
            @"exclusive move preserves competing destination and original");
        NSURL *link = [root URLByAppendingPathComponent:@"linked.app"];
        [fm createSymbolicLinkAtURL:link withDestinationURL:payload error:nil];
        error = nil;
        Require(!CheckApp(link, hash, &error), @"symlinked app is refused");
        Fixture(root, @"VODForge.app", @"new", @"0.2.7");
        before = Snapshot(destination);
        error = nil;
        Require(!CheckDestinationFolder(root, incoming, fm, NULL, &error) && error &&
            [Snapshot(destination) isEqual:before], @"newer destination preflight preserves app and requires fallback");
        error = nil;
        Require(!Install(payload, destination, hash, before, NULL, &error) &&
            [Snapshot(destination) isEqual:before], @"newer installed version is preserved");
        [fm removeItemAtURL:root error:nil];
        puts("Limits: compile-time signature/running-state substitutes; no native UI, actual running-app, Apple trust or installation outside owned temporary directory acceptance.");
    }
    return 0;
}
