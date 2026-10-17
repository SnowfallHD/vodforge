// Compile-time-only test harness. Not linked into the shipped installer.
#define VF_INSTALLER_CORE_TEST 1
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
        Require(!Install(payload, destination, hash, before, NULL, &error) &&
            [Snapshot(destination) isEqual:before], @"newer installed version is preserved");
        [fm removeItemAtURL:root error:nil];
        puts("Limits: compile-time signature/running-state substitutes; no native UI, actual running-app, Apple trust or installation outside owned temporary directory acceptance.");
    }
    return 0;
}
