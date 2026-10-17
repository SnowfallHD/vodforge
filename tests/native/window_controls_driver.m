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
static unsigned supportWrites, raiseSupportAt;
@class VFTestWindow;
@interface VFTestView : NSObject
@property(nonatomic) NSRect frame;
@property(nonatomic) NSRect bounds;
@property NSPoint windowOrigin;
@property BOOL flipped;
@property(retain) NSArray *subviews;
@property BOOL autoFill;
@property BOOL flexMinY;
@property BOOL raiseOnFrame;
- (BOOL)isFlipped;
- (BOOL)isRotatedOrScaledFromBase;
@property(assign) VFTestWindow *window;
@property(assign) VFTestView *superview;
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view;
- (NSRect)convertRect:(NSRect)rect fromView:(NSView *)view;
@end
@implementation VFTestView
@synthesize frame = _frame;
@synthesize bounds = _bounds;
- (BOOL)isFlipped { return self.flipped; }
- (BOOL)isRotatedOrScaledFromBase { return NO; }
- (void)setFrame:(NSRect)frame {
    if(self.raiseOnFrame){self.raiseOnFrame=NO;[NSException raise:@"childSetter" format:@"controlled"]; }
    if(self.subviews) {
        supportWrites++;
        if(raiseSupportAt && supportWrites==raiseSupportAt){raiseSupportAt=0;[NSException raise:@"supportSetter" format:@"controlled"];}
        double delta=frame.size.height-_frame.size.height;
        self.windowOrigin=NSMakePoint(self.windowOrigin.x+frame.origin.x-_frame.origin.x,self.windowOrigin.y+frame.origin.y-_frame.origin.y);
        _bounds.size=frame.size;
        _frame=frame;
        for(VFTestView *child in self.subviews) {
            NSRect next=child.frame;
            if(child.autoFill)next.size=frame.size;
            if(child.flexMinY)next.origin.y+=delta;
            child.frame=next;
        }
    }
    _frame=frame;
}
- (void)setBounds:(NSRect)bounds {
    if(self.subviews) {
        supportWrites++;
        if(raiseSupportAt && supportWrites==raiseSupportAt){raiseSupportAt=0;[NSException raise:@"supportSetter" format:@"controlled"];}
    }
    _bounds=bounds;
}
- (NSRect)toWindow:(NSRect)rect {
    double y = self.flipped ? self.bounds.size.height - (rect.origin.y-self.bounds.origin.y) - rect.size.height : rect.origin.y-self.bounds.origin.y;
    return NSMakeRect(rect.origin.x-self.bounds.origin.x + self.windowOrigin.x, y + self.windowOrigin.y, rect.size.width, rect.size.height);
}
- (NSRect)fromWindow:(NSRect)rect {
    rect.origin.x -= self.windowOrigin.x; rect.origin.y -= self.windowOrigin.y;
    if (self.flipped) rect.origin.y = self.bounds.size.height - rect.origin.y - rect.size.height;
    rect.origin.x+=self.bounds.origin.x;rect.origin.y+=self.bounds.origin.y;
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
- (void)dealloc { [_subviews release]; deallocViews++; [super dealloc]; }
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
    assert(owner && vf_window_controls_abi_version() == 2 && vf_window_controls_status(owner) == 1);
    assert(!window.toolbar && [window.appearance.name isEqualToString:NSAppearanceNameDarkAqua]);
    assertAligned(window); assert(writes == 3);
    assert(supportWrites==0);
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
    assert(vf_window_controls_diagnostic_reason() == 10);
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
        assert(vf_window_controls_diagnostic_reason() == 1);
        assert(isnan(vf_window_controls_diagnostic_geometry(0)));
        assert(!vf_window_controls_create(input->window, 18, 18));
        assert(vf_window_controls_reconcile(input->owner) == -1);
        assert(vf_window_controls_status(input->owner) == -1);
        void *same = input->owner;
        assert(vf_window_controls_destroy(&same) == 0 && same == input->owner);
    }
    return NULL;
}
static VFTestWindow *supportWindow(void) {
    VFTestWindow *window=[VFTestWindow new];VFTestView *parent=window->parents[0];
    parent.frame=NSMakeRect(0,0,1100,28);parent.bounds=NSMakeRect(0,0,1100,28);parent.windowOrigin=NSMakePoint(0,712);
    for(unsigned i=0;i<3;i++) {
        if(i){[window->parents[i] release];window->parents[i]=[parent retain];}
        window->buttons[i].superview=parent;window->buttons[i].frame=NSMakeRect(7+20*i,6,14,16);
    }
    VFTestView *background=[VFTestView new],*empty=[VFTestView new],*title=[VFTestView new];
    for(VFTestView *v in @[background,empty,title]){v.window=window;v.superview=parent;}
    background.frame=NSMakeRect(0,0,1100,28);background.autoFill=YES;
    title.frame=NSMakeRect(545,7,10,16);title.flexMinY=YES;
    parent.subviews=@[background,empty,window->buttons[0],window->buttons[1],window->buttons[2],title];
    [background release];[empty release];[title release];supportWrites=0;writes=0;return window;
}
static void assertSupportAligned(VFTestWindow *w) {
    NSRect expected=NSMakeRect(0,-6,1100,34);
    assert(NSEqualRects(w->parents[0].frame,expected));assert(NSEqualRects(w->parents[0].bounds,expected));
    for(unsigned i=0;i<3;i++)assert(NSEqualRects(w->buttons[i].frame,NSMakeRect(18+20*i,-6,14,16)));
}
static void testSupportBasic(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);
    assert(owner&&vf_window_controls_status(owner)==1);assertSupportAligned(w);
    assert(NSEqualRects(((VFTestView *)w->parents[0].subviews[0]).frame,NSMakeRect(0,0,1100,28)));
    assert(NSEqualRects(((VFTestView *)w->parents[0].subviews[5]).frame,NSMakeRect(545,7,10,16)));
    assert(vf_window_controls_destroy(&owner)==1);
    assert(NSEqualRects(w->parents[0].frame,NSMakeRect(0,0,1100,28)));
    assert(NSEqualRects(w->parents[0].bounds,NSMakeRect(0,0,1100,28)));
    for(unsigned i=0;i<3;i++)assert(NSEqualRects(w->buttons[i].frame,NSMakeRect(7+20*i,6,14,16)));
    [w release];
}
static void testSupportResize(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    VFTestView *p=w->parents[0];w->content.bounds=NSMakeRect(0,0,1300,900);
    p.frame=NSMakeRect(0,-6,1300,34);p.bounds=NSMakeRect(0,-6,1300,34);p.windowOrigin=NSMakePoint(0,866);
    assert(vf_window_controls_reconcile(owner)==1);assert(vf_window_controls_destroy(&owner)==1);
    assert(NSEqualRects(p.frame,NSMakeRect(0,0,1300,28)));assert(NSEqualRects(p.bounds,NSMakeRect(0,0,1300,28)));
    assert(p.windowOrigin.y==872);assert(((VFTestView *)p.subviews[0]).frame.size.width==1300);
    [w release];
}
static void testSupportFailure(void) {
    for(unsigned failure=1;failure<=3;failure++) {
        VFTestWindow *w=supportWindow();raiseSupportAt=failure<=2?failure:0;raiseAtWrite=failure==3?20:0;
        if(failure==3)raiseAtWrite=8; // parent resize3button writes + restoration3 + button owner second write
        void *owner=vf_window_controls_create(w,18,18);
        assert(!owner);assert(NSEqualRects(w->parents[0].frame,NSMakeRect(0,0,1100,28)));
        assert(NSEqualRects(w->parents[0].bounds,NSMakeRect(0,0,1100,28)));
        for(unsigned i=0;i<3;i++)assert(NSEqualRects(w->buttons[i].frame,NSMakeRect(7+20*i,6,14,16)));
        raiseAtWrite=raiseSupportAt=0;[w release];
    }
}
static void testSupportReset(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    VFTestView *p=w->parents[0];p.frame=NSMakeRect(0,0,1100,28);p.bounds=NSMakeRect(0,0,1100,28);p.windowOrigin=NSMakePoint(0,712);
    for(unsigned i=0;i<3;i++)w->buttons[i].frame=NSMakeRect(7+20*i,6,14,16);
    assert(vf_window_controls_reconcile(owner)==1);assertSupportAligned(w);
    vf_window_controls_destroy(&owner);[w release];
}
static void testSupportGuards(void) {
    for(unsigned mode=0;mode<3;mode++) {
        VFTestWindow *w=supportWindow();VFTestView *p=w->parents[0];
        if(mode==0)p.flipped=YES;
        if(mode==1)((VFTestView *)p.subviews[1]).frame=NSMakeRect(NAN,0,0,0);
        if(mode==2) {NSMutableArray *children=[p.subviews mutableCopy];for(unsigned i=0;i<27;i++){VFTestView *v=[VFTestView new];v.window=w;v.superview=p;[children addObject:v];[v release];}p.subviews=children;[children release];}
        supportWrites=0;void *owner=vf_window_controls_create(w,18,18);
        assert(!owner&&supportWrites==0);[w release];
    }
}
static void testSupportChildFailure(void) {
    VFTestWindow *w=supportWindow();VFTestView *p=w->parents[0];((VFTestView *)p.subviews[0]).raiseOnFrame=YES;
    void *owner=vf_window_controls_create(w,18,18);assert(!owner);
    assert(NSEqualRects(p.frame,NSMakeRect(0,0,1100,28)));assert(NSEqualRects(p.bounds,NSMakeRect(0,0,1100,28)));
    assert(p.windowOrigin.y==712);for(unsigned i=0;i<3;i++)assert(NSEqualRects(w->buttons[i].frame,NSMakeRect(7+20*i,6,14,16)));
    [w release];
}
static void testSupportNativeClose(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    writes=supportWrites=toolbarWrites=appearanceWrites=0;post(w,NSWindowWillCloseNotification);
    assert(writes==0&&supportWrites==0&&toolbarWrites==0&&appearanceWrites==0);
    post(w,NSWindowDidResizeNotification);assert(supportWrites==0);vf_window_controls_destroy(&owner);[w release];
}
static void testSupportResidual(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    VFTestView *p=w->parents[0];p.frame=NSMakeRect(0,0,1100,28);p.bounds=NSMakeRect(0,-6,1100,28);p.windowOrigin=NSMakePoint(0,712);
    for(unsigned i=0;i<3;i++)w->buttons[i].frame=NSMakeRect(7+20*i,6,14,16);
    supportWrites=0;assert(vf_window_controls_reconcile(owner)==1);assert(supportWrites>0);
    vf_window_controls_destroy(&owner);assert(p.bounds.origin.y==-6);assert(p.frame.size.height==28);[w release];
}
static void testSupportForeignRecovery(void) {
    VFTestWindow *w=supportWindow(),*other=[VFTestWindow new];void *owner=vf_window_controls_create(w,18,18);assert(owner);
    w->buttons[1].window=other;supportWrites=0;assert(vf_window_controls_reconcile(owner)==0&&supportWrites==0);
    w->buttons[1].window=w;assert(vf_window_controls_reconcile(owner)==1);vf_window_controls_destroy(&owner);assert(w->parents[0].frame.size.height==28);[w release];[other release];
}
static void testSupportInverseFailure(void) {
    VFTestWindow *w=supportWindow();NSButton *buttons[3]={(NSButton *)w->buttons[0],(NSButton *)w->buttons[1],(NSButton *)w->buttons[2]};
    VFSupportAdjustment *support=[[VFSupportAdjustment alloc] initWithWindow:(NSWindow *)w parent:(NSView *)w->parents[0] buttons:(NSButton **)buttons growth:6];assert(support);
    NSRect expandedFrame=w->parents[0].frame,expandedBounds=w->parents[0].bounds;
    NSRect before=[w->parents[0] convertRect:w->buttons[0].frame toView:nil];
    raiseSupportAt=supportWrites+2;assert(![support collapse]);assert(raiseSupportAt==0);
    assert(NSEqualRects(w->parents[0].frame,expandedFrame));assert(NSEqualRects(w->parents[0].bounds,expandedBounds));
    assert(NSEqualRects([w->parents[0] convertRect:w->buttons[0].frame toView:nil],before));assert([support current]);
    [support release];[w release];
}
static void testSupportReplacement(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    VFTestView *old=[w->parents[0] retain],*next=[VFTestView new];next.window=w;next.frame=NSMakeRect(0,0,1100,28);next.bounds=next.frame;next.windowOrigin=NSMakePoint(0,712);
    for(unsigned i=0;i<3;i++){w->buttons[i].superview=next;w->buttons[i].frame=NSMakeRect(7+20*i,6,14,16);[w->parents[i] release];w->parents[i]=[next retain];}
    next.subviews=@[w->buttons[0],w->buttons[1],w->buttons[2]];
    NSRect oldFrame=old.frame,oldBounds=old.bounds;
    assert(vf_window_controls_reconcile(owner)==1);vf_window_controls_destroy(&owner);
    assert(NSEqualRects(old.frame,oldFrame)&&NSEqualRects(old.bounds,oldBounds));
    assert(NSEqualRects(next.frame,NSMakeRect(0,0,1100,28))&&NSEqualRects(next.bounds,NSMakeRect(0,0,1100,28)));
    [next release];[old release];[w release];
}
static void testSupportNecessaryGrowth(void) {
    const double heights[]={20,28,30,34};
    for(unsigned mode=0;mode<4;mode++) {
        VFTestWindow *w=supportWindow();VFTestView *p=w->parents[0];double height=heights[mode];
        p.frame=NSMakeRect(0,0,1100,height);p.bounds=NSMakeRect(0,0,1100,height);p.windowOrigin=NSMakePoint(0,740-height);
        for(unsigned i=0;i<3;i++)w->buttons[i].frame=NSMakeRect(7+20*i,2,14,16);
        supportWrites=0;void *owner=vf_window_controls_create(w,18,18);assert(owner);
        assert(p.bounds.size.height==34);assert(p.bounds.origin.y==fmin(0,height-34));
        if(height==34)assert(supportWrites==0);
        vf_window_controls_destroy(&owner);assert(p.bounds.size.height==height&&p.bounds.origin.y==0);[w release];
    }
}
static void testDiagnostics(void) {
    VFTestWindow *window = [VFTestWindow new];
    NSObject *toolbar = [window->toolbarValue retain];
    window->parents[0].bounds = NSMakeRect(0, 0, 1100, 22);
    window->parents[0].windowOrigin = NSMakePoint(0, 718);
    writes = 0;
    void *owner = vf_window_controls_create(window, 18, 18);
    assert(!owner && writes == 0 && vf_window_controls_diagnostic_reason() == 8);
    assert(vf_window_controls_diagnostic_geometry(11) == 22);
    assert(vf_window_controls_diagnostic_geometry(13) == -10);
    assert(window->toolbarValue == toolbar && window.appearance == nil);
    window->parents[0].bounds = NSMakeRect(0, 0, 1100, 32);
    window->parents[0].windowOrigin = NSMakePoint(0, 708);
    owner = vf_window_controls_create(window, 18, 18); assert(owner);
    assert(vf_window_controls_diagnostic_reason() == 0);
    VFTestWindow *foreign = [VFTestWindow new]; window->buttons[1].window = foreign;
    assert(vf_window_controls_reconcile(owner) == 0 && vf_window_controls_diagnostic_reason() == 5);
    window->buttons[1].window = window;
    assert(vf_window_controls_reconcile(owner) == 1 && vf_window_controls_diagnostic_reason() == 0);
    assert(isnan(vf_window_controls_diagnostic_geometry(40)));
    vf_window_controls_destroy(&owner); [toolbar release]; [foreign release]; [window release];
}
static void testSupportThread(void) {
    VFTestWindow *w=supportWindow();void *owner=vf_window_controls_create(w,18,18);assert(owner);
    writes=supportWrites=toolbarWrites=appearanceWrites=0;VFThreadInput input={w,owner};pthread_t thread;
    assert(pthread_create(&thread,NULL,wrongThread,&input)==0);assert(pthread_join(thread,NULL)==0);
    assert(writes==0&&supportWrites==0&&toolbarWrites==0&&appearanceWrites==0);
    vf_window_controls_destroy(&owner);assert(w->parents[0].bounds.size.height==28);[w release];
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
    assert(vf_window_controls_diagnostic_reason() == 0);
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
        else if (!strcmp(argv[1], "diagnostics")) testDiagnostics();
        else if (!strcmp(argv[1], "support_basic")) testSupportBasic();
        else if (!strcmp(argv[1], "support_resize")) testSupportResize();
        else if (!strcmp(argv[1], "support_failure")) testSupportFailure();
        else if (!strcmp(argv[1], "support_reset")) testSupportReset();
        else if (!strcmp(argv[1], "support_guards")) testSupportGuards();
        else if (!strcmp(argv[1], "support_child_failure")) testSupportChildFailure();
        else if (!strcmp(argv[1], "support_native_close")) testSupportNativeClose();
        else if (!strcmp(argv[1], "support_residual")) testSupportResidual();
        else if (!strcmp(argv[1], "support_foreign_recovery")) testSupportForeignRecovery();
        else if (!strcmp(argv[1], "support_inverse_failure")) testSupportInverseFailure();
        else if (!strcmp(argv[1], "support_replacement")) testSupportReplacement();
        else if (!strcmp(argv[1], "support_necessary_growth")) testSupportNecessaryGrowth();
        else if (!strcmp(argv[1], "support_thread")) testSupportThread();
        else return 2;
        assert(NSApp == nil);
        printf("{\"case\":\"%s\",\"passed\":true,\"gui_created\":false}\n", argv[1]);
    }
    return 0;
}
