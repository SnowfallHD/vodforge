// Headless public-boundary doubles exercise the actual compiled production owner.
// No NSApplication, NSWindow allocation, display, AX, input or screenshots.
#import <AppKit/AppKit.h>
#include <assert.h>
#include <math.h>
#include <float.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#import "../../yt_downloader/platforms/macos/fullscreen_lifecycle.m"

static unsigned writes, deallocButtons, deallocWindows, deallocViews;
static unsigned raiseAtWrite;
static unsigned toolbarWrites, appearanceWrites;
@class VFTestWindow;
@interface VFTestView : NSObject
@property NSRect frame;
@property NSRect bounds;
@property NSPoint windowOrigin;
@property BOOL flipped;
@property(assign) VFTestWindow *window;
@property(assign) VFTestView *superview;
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view;
- (NSRect)convertRect:(NSRect)rect fromView:(NSView *)view;
@end
@implementation VFTestView
- (NSRect)toWindow:(NSRect)rect {
    double y = self.flipped ? self.bounds.size.height - rect.origin.y - rect.size.height : rect.origin.y;
    return NSMakeRect(rect.origin.x + self.windowOrigin.x, y + self.windowOrigin.y, rect.size.width, rect.size.height);
}
- (NSRect)fromWindow:(NSRect)rect {
    rect.origin.x -= self.windowOrigin.x; rect.origin.y -= self.windowOrigin.y;
    if (self.flipped) rect.origin.y = self.bounds.size.height - rect.origin.y - rect.size.height;
    return rect;
}
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view {
    rect = [self toWindow:rect];
    return view ? [(VFTestView *)view fromWindow:rect] : rect;
}
- (NSRect)convertRect:(NSRect)rect fromView:(NSView *)view {
    if (view) rect = [(VFTestView *)view toWindow:rect];
    return [self fromWindow:rect];
}
- (void)dealloc { deallocViews++; [super dealloc]; }
@end

@interface VFTestButton : VFTestView
@end
@implementation VFTestButton
- (void)setFrame:(NSRect)frame {
    writes++;
    if (raiseAtWrite && writes == raiseAtWrite) {
        raiseAtWrite = 0;
        [NSException raise:@"testSetter" format:@"controlled frame setter failure"];
    }
    [super setFrame:frame];
}
- (void)dealloc { deallocButtons++; [super dealloc]; }
@end

@interface VFTestWindow : NSObject {
@public
    VFTestView *content;
    VFTestView *parents[3];
    VFTestButton *buttons[3];
    NSObject *toolbarValue;
    NSAppearance *appearanceValue;
}
- (NSView *)contentView;
- (NSButton *)standardWindowButton:(NSWindowButton)which;
- (NSToolbar *)toolbar;
- (void)setToolbar:(NSToolbar *)value;
- (NSAppearance *)appearance;
- (void)setAppearance:(NSAppearance *)value;
@end
@implementation VFTestWindow
- (instancetype)init {
    self = [super init];
    if (!self) return nil;
    content = [VFTestView new]; content.window = self;
    content.bounds = NSMakeRect(0, 0, 1100, 740); content.windowOrigin = NSMakePoint(0, 0);
    for (unsigned i = 0; i < 3; i++) {
        parents[i] = [VFTestView new]; parents[i].window = self;
        parents[i].bounds = NSMakeRect(0, 0, 1100, 32); parents[i].windowOrigin = NSMakePoint(0, 708);
        buttons[i] = [VFTestButton new]; buttons[i].window = self; buttons[i].superview = parents[i];
        buttons[i].frame = NSMakeRect(9 + 23 * i, 9, 14, 14);
    }
    toolbarValue = [NSObject new]; return self;
}
- (BOOL)isKindOfClass:(Class)class { return class == [NSWindow class] || [super isKindOfClass:class]; }
- (NSView *)contentView { return (NSView *)content; }
- (NSButton *)standardWindowButton:(NSWindowButton)which { return which <= 2 ? (NSButton *)buttons[which] : nil; }
- (NSToolbar *)toolbar { return (NSToolbar *)toolbarValue; }
- (void)setToolbar:(NSToolbar *)value { toolbarWrites++; [value retain]; [toolbarValue release]; toolbarValue = (id)value; }
- (NSAppearance *)appearance { return appearanceValue; }
- (void)setAppearance:(NSAppearance *)value { appearanceWrites++; [value retain]; [appearanceValue release]; appearanceValue = value; }
- (void)dealloc {
    for (unsigned i = 0; i < 3; i++) { [buttons[i] release]; [parents[i] release]; }
    [content release]; [toolbarValue release]; [appearanceValue release];
    deallocWindows++; [super dealloc];
}
@end

static void post(VFTestWindow *window, NSNotificationName name) {
    [[NSNotificationCenter defaultCenter] postNotificationName:name object:window];
}
static void assertAligned(VFTestWindow *window) {
    for (unsigned i = 0; i < 3; i++) {
        NSRect expected = NSMakeRect(18 + 23 * i, 0, 14, 14);
        assert(NSEqualRects(window->buttons[i].frame, expected));
    }
}
static void replaceButton(VFTestWindow *window, unsigned index, NSRect frame) {
    VFTestButton *button = [VFTestButton new]; button.window = window;
    button.superview = window->parents[index]; button.frame = frame;
    [window->buttons[index] release]; window->buttons[index] = button;
}
static void testBasic(void) {
    VFTestWindow *window = [VFTestWindow new]; writes = 0;
    NSObject *toolbar = [window->toolbarValue retain];
    void *owner = vf_window_controls_create(window, 18, 18);
    assert(owner && vf_window_controls_abi_version() == 1 && vf_window_controls_status(owner) == 1);
    assert(!window.toolbar && [window.appearance.name isEqualToString:NSAppearanceNameDarkAqua]);
    assertAligned(window); assert(writes == 3);
    writes = 0; assert(vf_window_controls_reconcile(owner) == 1 && writes == 0);
    assert(vf_window_controls_destroy(&owner) == 1 && !owner);
    assert(vf_window_controls_destroy(&owner) == 1);
    assert(window->toolbarValue == toolbar && window.appearance == nil);
    for (unsigned i = 0; i < 3; i++) assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(9 + 23 * i, 9, 14, 14)));
    writes = 0; post(window, NSWindowDidResizeNotification); assert(writes == 0);
    [toolbar release]; [window release]; assert(deallocButtons == 3 && deallocWindows == 1 && deallocViews == 7);
}
static void testBoundsAndFinite(void) {
    assert(!VFValidRect(NSMakeRect(DBL_MAX, 0, DBL_MAX, 32)));
    assert(!VFValidRect(NSMakeRect(0, DBL_MAX, 32, DBL_MAX)));
    for (unsigned mode = 0; mode < 5; mode++) {
        VFTestWindow *window = [VFTestWindow new];
        if (mode == 0) window->parents[2].bounds = NSMakeRect(0, 0, 60, 32);
        if (mode == 1) window->buttons[2].frame = NSMakeRect(55, 9, 14, 16);
        if (mode == 2) window->parents[1].windowOrigin = NSMakePoint(0, 730);
        if (mode == 3) window->buttons[2].frame = NSMakeRect(NAN, 9, 14, 14);
        if (mode == 4) window->content.bounds = NSMakeRect(0, 0, INFINITY, 740);
        NSObject *toolbar = [window->toolbarValue retain]; writes = 0;
        void *owner = vf_window_controls_create(window, 18, 18);
        assert(!owner && writes == 0 && window->toolbarValue == toolbar && !window.appearance);
        [toolbar release]; [window release];
    }
    assert(!vf_window_controls_create(NULL, 18, 18));
    VFTestWindow *window = [VFTestWindow new]; writes = 0;
    assert(!vf_window_controls_create(window, NAN, 18));
    assert(!vf_window_controls_create(window, -1, 18)); assert(writes == 0); [window release];
}
static void testForeignAndRecovery(void) {
    VFTestWindow *window = [VFTestWindow new], *foreign = [VFTestWindow new];
    void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    // Foreign notifications cannot alter the current exact window.
    for (unsigned i = 0; i < 3; i++) window->buttons[i].frame = NSMakeRect(9 + 23 * i, 9, 14, 14);
    writes = 0;
    post(foreign, NSWindowDidResizeNotification); assert(writes == 0);
    window->buttons[2].window = foreign;
    assert(vf_window_controls_reconcile(owner) == 0 && writes == 0);
    // A transition can be abandoned without a did notification. Latest owned
    // geometry reconciliation recovers without a pending phase or toolbar state.
    window->buttons[2].window = window;
    post(window, NSWindowDidResizeNotification); assert(vf_window_controls_status(owner) == 1);
    assertAligned(window); assert(!window.toolbar);
    vf_window_controls_destroy(&owner); [window release]; [foreign release];
}
static void testReparent(BOOL reconcileFirst) {
    VFTestWindow *window = [VFTestWindow new];
    void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    for (unsigned i = 0; i < 3; i++) {
        VFTestView *parent = [VFTestView new]; parent.window = window;
        parent.bounds = NSMakeRect(0, 0, 1100, 32); parent.windowOrigin = NSMakePoint(0, 708);
        window->buttons[i].superview = parent;
        window->buttons[i].frame = NSMakeRect(6 + 20 * i, 4, 14, 14);
        [window->parents[i] release]; window->parents[i] = parent;
    }
    if (reconcileFirst) {
        assert(vf_window_controls_reconcile(owner) == 1);
        for (unsigned i = 0; i < 3; i++)
            assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(18 + 20 * i, 0, 14, 14)));
    }
    vf_window_controls_destroy(&owner);
    for (unsigned i = 0; i < 3; i++)
        assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(6 + 20 * i, 4, 14, 14)));
    [window release]; assert(deallocViews == 10); // three parent generations released
}
static void testReplacement(void) {
    VFTestWindow *window = [VFTestWindow new]; void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    VFTestButton *old = [window->buttons[0] retain]; NSRect oldFrame = old.frame;
    replaceButton(window, 0, NSMakeRect(9, 9, 14, 14));
    // Admission fails for the full replacement set: it must not replace held
    // references, release originals, or perform the first button write early.
    window->parents[2].bounds = NSMakeRect(0, 0, 60, 32); writes = 0;
    assert(vf_window_controls_reconcile(owner) == 0 && writes == 0);
    assert(NSEqualRects(old.frame, oldFrame));
    window->parents[2].bounds = NSMakeRect(0, 0, 1100, 32);
    for (unsigned i = 1; i < 3; i++) replaceButton(window, i, NSMakeRect(9 + 23 * i, 9, 14, 14));
    assert(vf_window_controls_reconcile(owner) == 1); assertAligned(window);
    vf_window_controls_destroy(&owner);
    assert(NSEqualRects(old.frame, oldFrame)); // stale receiver never restored
    assert(NSEqualRects(window->buttons[0].frame, NSMakeRect(9, 9, 14, 14)));
    [old release]; [window release];
}
static void testSetterFailure(void) {
    VFTestWindow *window = [VFTestWindow new]; NSObject *toolbar = [window->toolbarValue retain];
    writes = 0; raiseAtWrite = 2;
    void *owner = vf_window_controls_create(window, 18, 18);
    assert(!owner && !raiseAtWrite && window->toolbarValue == toolbar && !window.appearance);
    for (unsigned i = 0; i < 3; i++) assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(9 + 23 * i, 9, 14, 14)));
    [toolbar release]; [window release];
}
static void testFlippedAndResize(void) {
    VFTestWindow *window = [VFTestWindow new];
    for (unsigned i = 0; i < 3; i++) window->parents[i].flipped = YES;
    NSAppearance *original = [NSAppearance appearanceNamed:NSAppearanceNameAqua]; window.appearance = original;
    void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    for (unsigned i = 0; i < 3; i++) assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(18 + 23 * i, 18, 14, 14)));
    window->content.bounds = NSMakeRect(0, 0, 1200, 900);
    for (unsigned i = 0; i < 3; i++) {
        window->parents[i].bounds = NSMakeRect(0, 0, 1200, 32);
        window->parents[i].windowOrigin = NSMakePoint(0, 868);
    }
    post(window, NSWindowDidResizeNotification); assert(vf_window_controls_status(owner) == 1);
    for (unsigned i = 0; i < 3; i++) assert(NSEqualRects(window->buttons[i].frame, NSMakeRect(18 + 23 * i, 18, 14, 14)));
    vf_window_controls_destroy(&owner); assert(window.appearance == original); [window release];
}
static void testCloseAndLate(void) {
    VFTestWindow *window = [VFTestWindow new]; void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    writes = toolbarWrites = appearanceWrites = 0;
    post(window, NSWindowWillCloseNotification); assert(vf_window_controls_status(owner) == -1);
    assert(writes == 0 && toolbarWrites == 0 && appearanceWrites == 0);
    assert(!window.toolbar && [window.appearance.name isEqualToString:NSAppearanceNameDarkAqua]);
    assertAligned(window); // do not move controls back while native close is underway
    writes = 0; post(window, NSWindowDidExitFullScreenNotification);
    assert(vf_window_controls_reconcile(owner) == -1 && writes == 0);
    assert(vf_window_controls_destroy(&owner) == 1 && !owner);
    assert(vf_window_controls_destroy(&owner) == 1 && writes == 0);
    [window release]; assert(deallocButtons == 3 && deallocWindows == 1 && deallocViews == 7);
}
typedef struct { VFTestWindow *window; void *owner; } VFThreadInput;
static void *wrongThread(void *raw) {
    @autoreleasepool {
        VFThreadInput *input = raw;
        assert(![NSThread isMainThread]);
        assert(!vf_window_controls_create(input->window, 18, 18));
        assert(vf_window_controls_reconcile(input->owner) == -1);
        assert(vf_window_controls_status(input->owner) == -1);
        void *same = input->owner;
        assert(vf_window_controls_destroy(&same) == 0 && same == input->owner);
    }
    return NULL;
}
static void testWrongThread(void) {
    VFTestWindow *window = [VFTestWindow new]; void *owner = vf_window_controls_create(window, 18, 18); assert(owner);
    NSUInteger windowRetains = window.retainCount, buttonRetains[3], parentRetains[3];
    for (unsigned i = 0; i < 3; i++) {
        buttonRetains[i] = window->buttons[i].retainCount;
        parentRetains[i] = window->parents[i].retainCount;
    }
    writes = toolbarWrites = appearanceWrites = 0;
    VFThreadInput input = {window, owner}; pthread_t thread;
    assert(pthread_create(&thread, NULL, wrongThread, &input) == 0);
    assert(pthread_join(thread, NULL) == 0);
    assert(writes == 0 && toolbarWrites == 0 && appearanceWrites == 0);
    assert(window.retainCount == windowRetains && vf_window_controls_status(owner) == 1);
    for (unsigned i = 0; i < 3; i++) {
        assert(window->buttons[i].retainCount == buttonRetains[i]);
        assert(window->parents[i].retainCount == parentRetains[i]);
    }
    assertAligned(window);
    assert(vf_window_controls_destroy(&owner) == 1 && !owner); [window release];
    assert(deallocButtons == 3 && deallocViews == 7 && deallocWindows == 1);
}
int main(int argc, const char **argv) {
    @autoreleasepool {
        assert(argc == 2); assert([NSThread isMainThread]); assert(NSApp == nil);
        if (!strcmp(argv[1], "basic")) testBasic();
        else if (!strcmp(argv[1], "bounds_finite")) testBoundsAndFinite();
        else if (!strcmp(argv[1], "foreign_recovery")) testForeignAndRecovery();
        else if (!strcmp(argv[1], "replacement")) testReplacement();
        else if (!strcmp(argv[1], "setter_failure")) testSetterFailure();
        else if (!strcmp(argv[1], "flipped_resize")) testFlippedAndResize();
        else if (!strcmp(argv[1], "close_late")) testCloseAndLate();
        else if (!strcmp(argv[1], "reparent_reconcile")) testReparent(YES);
        else if (!strcmp(argv[1], "reparent_stale_close")) testReparent(NO);
        else if (!strcmp(argv[1], "wrong_thread")) testWrongThread();
        else return 2;
        assert(NSApp == nil);
        printf("{\"case\":\"%s\",\"passed\":true,\"gui_created\":false}\n", argv[1]);
    }
    return 0;
}
