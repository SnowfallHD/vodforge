// Public AppKit window controls. No Python callbacks, private frame access,
// delegate replacement, runtime compilation or fullscreen timing assumptions.
#import <AppKit/AppKit.h>
#include <math.h>

// Main-thread diagnostic scalars only. No user strings or private view data.
static int VFDiagnosticReason;
static double VFDiagnosticGeometry[40];
static void VFResetDiagnostic(void) {
    VFDiagnosticReason = 0;
    for (unsigned i=0; i<40; i++) VFDiagnosticGeometry[i] = NAN;
}
static void VFRecordRect(unsigned offset, NSRect r) {
    VFDiagnosticGeometry[offset] = r.origin.x; VFDiagnosticGeometry[offset+1] = r.origin.y;
    VFDiagnosticGeometry[offset+2] = r.size.width; VFDiagnosticGeometry[offset+3] = r.size.height;
}
static BOOL VFValidRect(NSRect rect) {
    return isfinite(rect.origin.x) && isfinite(rect.origin.y)
        && isfinite(rect.size.width) && isfinite(rect.size.height)
        && isfinite(NSMaxX(rect)) && isfinite(NSMaxY(rect))
        && rect.size.width > 0 && rect.size.height > 0;
}

static BOOL VFChildRect(NSRect r) {
    return isfinite(r.origin.x) && isfinite(r.origin.y) && isfinite(r.size.width)
        && isfinite(r.size.height) && isfinite(NSMaxX(r)) && isfinite(NSMaxY(r))
        && r.size.width >= 0 && r.size.height >= 0;
}
static BOOL VFRectNear(NSRect a, NSRect b) {
    return fabs(a.origin.x-b.origin.x)<.01 && fabs(a.origin.y-b.origin.y)<.01
        && fabs(a.size.width-b.size.width)<.01 && fabs(a.size.height-b.size.height)<.01;
}

// One exact public immediate support view. Never access its ancestors/classes.
@interface VFSupportAdjustment : NSObject {
    NSWindow *_window;
    NSView *_parent;
    NSArray *_children;
    NSButton *_buttons[3]; // retained by the exact children snapshot
    double _growth, _baseY, _baseHeight;
}
- (instancetype)initWithWindow:(NSWindow *)window parent:(NSView *)parent buttons:(NSButton **)buttons growth:(double)growth;
- (BOOL)generation;
- (BOOL)current;
- (BOOL)collapse;
@end
@implementation VFSupportAdjustment
- (BOOL)generation {
    NSArray *current=_parent.subviews;
    if (_parent.window != _window || current.count!=_children.count) return NO;
    for(NSUInteger i=0;i<_children.count;i++)if(current[i]!=_children[i])return NO;
    for (NSView *v in _children) if (v.superview != _parent || v.window != _window) return NO;
    for (unsigned i=0;i<3;i++) if ([_window standardWindowButton:(NSWindowButton)i]!=_buttons[i]
        || _buttons[i].superview!=_parent || _buttons[i].window!=_window) return NO;
    return YES;
}
- (BOOL)current {
    if (![self generation] || _parent.isFlipped || _parent.isRotatedOrScaledFromBase) return NO;
    NSRect frame=_parent.frame, bounds=_parent.bounds;
    return VFValidRect(frame) && VFValidRect(bounds)
        && fabs(frame.size.width-bounds.size.width)<.01
        && fabs(frame.size.height-(_baseHeight+_growth))<.01
        && fabs(bounds.size.height-(_baseHeight+_growth))<.01
        && fabs(bounds.origin.y-(_baseY-_growth))<.01;
}
- (instancetype)initWithWindow:(NSWindow *)window parent:(NSView *)parent buttons:(NSButton **)buttons growth:(double)growth {
    self=[super init]; if(!self)return nil;
    _window=[window retain]; _parent=[parent retain]; _children=[parent.subviews copy];
    for(unsigned i=0;i<3;i++)_buttons[i]=buttons[i];
    NSRect originalFrame=parent.frame, originalBounds=parent.bounds;
    NSRect originalWindow=[parent convertRect:parent.bounds toView:nil];
    _growth=growth;_baseY=originalBounds.origin.y;_baseHeight=originalBounds.size.height;
    NSUInteger count=_children.count;
    NSRect frames[32], windows[32]; BOOL changed=NO, valid=NO;
    @try {
        if(count>32 || count<3 || ![self generation] || parent.isFlipped || parent.isRotatedOrScaledFromBase
            || !VFValidRect(originalFrame) || !VFValidRect(originalBounds) || !VFValidRect(originalWindow)
            || !isfinite(growth) || growth<=0 || growth>64
            || fabs(originalFrame.size.width-originalBounds.size.width)>.01
            || fabs(originalFrame.size.height-originalBounds.size.height)>.01
            || fabs(originalWindow.size.width-originalBounds.size.width)>.01
            || fabs(originalWindow.size.height-originalBounds.size.height)>.01) goto finish;
        for(unsigned i=0;i<3;i++)if(![_children containsObject:buttons[i]])goto finish;
        for(NSUInteger i=0;i<count;i++) {
            NSView *v=_children[i];frames[i]=v.frame;windows[i]=[parent convertRect:v.frame toView:nil];
            if(!VFChildRect(frames[i])||!VFChildRect(windows[i]))goto finish;
        }
        NSRect frame=originalFrame,bounds=originalBounds;
        frame.origin.y-=growth;frame.size.height+=growth;
        bounds.origin.y-=growth;bounds.size.height+=growth;
        if(!VFValidRect(frame)||!VFValidRect(bounds))goto finish;
        changed=YES;parent.frame=frame;
        if(![self generation])goto finish;
        parent.bounds=bounds;
        for(NSUInteger i=0;i<count;i++) {
            if(![self generation])goto finish;
            ((NSView *)_children[i]).frame=frames[i];
        }
        NSRect current=[parent convertRect:parent.bounds toView:nil];
        if(![self current]||!VFValidRect(current)||fabs(NSMaxY(current)-NSMaxY(originalWindow))>.01
            || fabs(current.size.width-originalWindow.size.width)>.01)goto finish;
        for(NSUInteger i=0;i<count;i++)if(!VFRectNear([parent convertRect:((NSView *)_children[i]).frame toView:nil],windows[i]))goto finish;
        valid=YES;
    } @catch(NSException *exception) {(void)exception;}
finish:
    if(!valid) {
        // Immediate partial rollback: all snapshots precede this transaction.
        if(changed) @try {
            if([self generation]) {
                parent.frame=originalFrame;
                if([self generation])parent.bounds=originalBounds;
                for(NSUInteger i=0;i<count&&i<32;i++) {
                    if(![self generation])break;
                    ((NSView *)_children[i]).frame=frames[i];
                }
            }
        } @catch(NSException *exception) {(void)exception;}
        [self release];return nil;
    }
    return self;
}
- (BOOL)collapse {
    if(![self current])return NO;
    NSUInteger count=_children.count;NSRect frames[32], windows[32];
    NSRect beforeFrame=_parent.frame,beforeBounds=_parent.bounds;
    BOOL changed=NO,valid=NO;
    @try {
        for(NSUInteger i=0;i<count;i++) {
            NSView *v=_children[i];frames[i]=v.frame;windows[i]=[_parent convertRect:v.frame toView:nil];
            if(!VFChildRect(frames[i])||!VFChildRect(windows[i]))goto finish;
        }
        // Invert only our delta in CURRENT geometry; retain resized width/top.
        NSRect frame=beforeFrame,bounds=beforeBounds;
        frame.origin.y+=_growth;frame.size.height-=_growth;
        bounds.origin.y+=_growth;bounds.size.height-=_growth;
        if(!VFValidRect(frame)||!VFValidRect(bounds))goto finish;
        changed=YES;_parent.frame=frame;
        if(![self generation])goto finish;
        _parent.bounds=bounds;
        for(NSUInteger i=0;i<count;i++) {
            if(![self generation])goto finish;
            ((NSView *)_children[i]).frame=frames[i];
        }
        for(NSUInteger i=0;i<count;i++)if(!VFRectNear([_parent convertRect:((NSView *)_children[i]).frame toView:nil],windows[i]))goto finish;
        valid=YES;
    } @catch(NSException *exception) {(void)exception;}
finish:
    if(changed&&!valid) @try {
        // A failed inverse remains expanded instead of leaving a partial map.
        if([self generation]) {
            _parent.frame=beforeFrame;
            if([self generation])_parent.bounds=beforeBounds;
            for(NSUInteger i=0;i<count;i++) {
                if(![self generation])break;
                ((NSView *)_children[i]).frame=frames[i];
            }
        }
    } @catch(NSException *exception) {(void)exception;}
    return valid;
}
- (void)dealloc {[_children release];[_parent release];[_window release];[super dealloc];}
@end

@interface VFWindowControlsOwner : NSObject {
@public
    NSWindow *_window;
    NSToolbar *_originalToolbar;
    NSAppearance *_originalAppearance;
    NSButton *_buttons[3];
    NSView *_parents[3];
    NSRect _originalFrames[3];
    double _horizontalInset;
    double _topInset;
    BOOL _closed;
    BOOL _reconciling;
    BOOL _closingWindow;
    int _status;
    VFSupportAdjustment *_support;
}
- (instancetype)initWithWindow:(NSWindow *)window horizontal:(double)x top:(double)top;
- (int)reconcile;
- (void)changed:(NSNotification *)notification;
- (void)willClose:(NSNotification *)notification;
- (void)close;
@end

@implementation VFWindowControlsOwner
- (instancetype)initWithWindow:(NSWindow *)window horizontal:(double)x top:(double)top {
    self = [super init];
    if (!self) return nil;
    _window = [window retain];
    _horizontalInset = x;
    _topInset = top;
    _status = 0;
    @try {
        _originalToolbar = [window.toolbar retain];
        _originalAppearance = [window.appearance retain];
        NSAppearance *dark = [NSAppearance appearanceNamed:NSAppearanceNameDarkAqua];
        if (!dark) { VFDiagnosticReason = 3; [self release]; return nil; }
        // Every product theme is dark. Affect this exact window only, never the
        // application/global preference. Preserve nil (inherited) appearance too.
        window.appearance = dark;
        // An empty unified toolbar occludes expanded Qt content during native
        // animation/reveal and changes traffic-light layout on reattachment.
        // Its absence is invariant, not an asynchronous fullscreen phase policy.
        window.toolbar = nil;
        if ([self reconcile] != 1) { [self release]; return nil; }
        NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
        for (NSNotificationName name in @[NSWindowDidResizeNotification,
             NSWindowWillEnterFullScreenNotification, NSWindowDidEnterFullScreenNotification,
             NSWindowWillExitFullScreenNotification, NSWindowDidExitFullScreenNotification]) {
            [center addObserver:self selector:@selector(changed:) name:name object:window];
        }
        [center addObserver:self selector:@selector(willClose:) name:NSWindowWillCloseNotification object:window];
    } @catch (NSException *exception) {
        (void)exception;
        VFDiagnosticReason = 11;
        [self release];
        return nil;
    }
    return self;
}

- (int)reconcile {
    if (_closed || ![NSThread isMainThread]) return -1;
    if (_reconciling) return _status;
    _reconciling = YES;
    VFResetDiagnostic();
    NSButton *candidates[3] = {nil, nil, nil};
    NSView *parents[3] = {nil, nil, nil};
    NSRect current[3], windowFrames[3], targets[3];
    BOOL retained[3] = {NO, NO, NO};
    BOOL parentsRetained[3] = {NO, NO, NO};
    BOOL writesStarted = NO;
    BOOL createdSupport = NO;
    int result = 0;
    @try {
        NSView *content = _window.contentView;
        if (!content || content.window != _window || !VFValidRect(content.bounds)) { VFDiagnosticReason=4; goto done; }
        NSRect contentWindow = [content convertRect:content.bounds toView:nil];
        VFRecordRect(0, contentWindow);
        if (!VFValidRect(contentWindow)) { VFDiagnosticReason=4; goto done; }
        for (unsigned i = 0; i < 3; i++) {
            candidates[i] = [_window standardWindowButton:(NSWindowButton)i];
            if (!candidates[i] || candidates[i].window != _window) { VFDiagnosticReason=5; goto done; }
            // AppKit may temporarily reparent or replace fullscreen controls.
            // Inspect only each current public button and its immediate view.
            parents[i] = candidates[i].superview;
            if (!parents[i] || parents[i].window != _window || !VFValidRect(parents[i].bounds)) { VFDiagnosticReason=6; goto done; }
            VFRecordRect(8+12*i, parents[i].bounds);
            current[i] = candidates[i].frame;
            if (!VFValidRect(current[i])) { VFDiagnosticReason=5; goto done; }
            windowFrames[i] = [parents[i] convertRect:current[i] toView:nil];
            VFRecordRect(4+12*i, windowFrames[i]);
            if (!VFValidRect(windowFrames[i])) { VFDiagnosticReason=5; goto done; }
        }
        if (_support && ![_support current]) {
            // Native reset/replacement: relinquish stale ownership without writes.
            [_support release]; _support=nil;
            for(unsigned i=0;i<3;i++) {[_buttons[i] release];_buttons[i]=nil;[_parents[i] release];_parents[i]=nil;}
        }
        double growth=0; BOOL outside=NO;
        NSRect windowTargets[3];
        for (unsigned i = 0; i < 3; i++) {
            double x = NSMinX(contentWindow) + _horizontalInset
                + NSMinX(windowFrames[i]) - NSMinX(windowFrames[0]);
            double y = NSMaxY(contentWindow) - _topInset - windowFrames[i].size.height;
            NSRect windowTarget = NSMakeRect(x, y, windowFrames[i].size.width, windowFrames[i].size.height);
            if (!VFValidRect(windowTarget)) { VFDiagnosticReason=7; goto done; }
            windowTargets[i]=windowTarget;
            targets[i] = [parents[i] convertRect:windowTarget fromView:nil];
            VFRecordRect(12+12*i, targets[i]);
            if (!VFValidRect(targets[i])) { VFDiagnosticReason=7; goto done; }
            if (!NSContainsRect(parents[i].bounds, targets[i])) {
                outside=YES;
                NSRect bounds=parents[i].bounds;
                if(NSMinX(targets[i])<NSMinX(bounds)||NSMaxX(targets[i])>NSMaxX(bounds)||NSMaxY(targets[i])>NSMaxY(bounds)) {VFDiagnosticReason=8;goto done;}
                growth=fmax(growth,NSMinY(bounds)-NSMinY(targets[i]));
            }
        }
        if(outside) {
            if(_support||parents[0]!=parents[1]||parents[0]!=parents[2]||growth<=0||growth>fmin(64,_topInset+windowFrames[0].size.height)) {VFDiagnosticReason=8;goto done;}
            _support=[[VFSupportAdjustment alloc] initWithWindow:_window parent:parents[0] buttons:candidates growth:growth];
            if(!_support){VFDiagnosticReason=12;goto done;}
            createdSupport=YES;
            for(unsigned i=0;i<3;i++) {
                if([_window standardWindowButton:(NSWindowButton)i]!=candidates[i]||candidates[i].superview!=parents[i]){VFDiagnosticReason=9;goto done;}
                current[i]=candidates[i].frame;
                targets[i]=[parents[i] convertRect:windowTargets[i] fromView:nil];
                VFRecordRect(8+12*i,parents[i].bounds);VFRecordRect(12+12*i,targets[i]);
                if(!VFValidRect(targets[i])||!NSContainsRect(parents[i].bounds,targets[i])){VFDiagnosticReason=8;goto done;}
            }
        }
        // Retain replacements only after ALL current receivers and targets pass.
        for (unsigned i = 0; i < 3; i++) {
            [candidates[i] retain]; retained[i] = YES;
            [parents[i] retain]; parentsRetained[i] = YES;
        }
        // Revalidate identity after admission and before the first mutation.
        for (unsigned i = 0; i < 3; i++) {
            if ([_window standardWindowButton:(NSWindowButton)i] != candidates[i]
                || candidates[i].window != _window || candidates[i].superview != parents[i]) { VFDiagnosticReason=9; goto done; }
        }
        writesStarted = YES;
        for (unsigned i = 0; i < 3; i++) {
            if (!NSEqualRects(candidates[i].frame, targets[i])) candidates[i].frame = targets[i];
        }
        for (unsigned i = 0; i < 3; i++) {
            if (_buttons[i] != candidates[i] || _parents[i] != parents[i]) {
                // Never restore a stale/replaced receiver. Its original snapshot
                // belongs to that receiver, not a subsequent AppKit replacement.
                [_buttons[i] release];
                [_parents[i] release];
                _buttons[i] = candidates[i]; retained[i] = NO;
                _parents[i] = parents[i]; parentsRetained[i] = NO;
                _originalFrames[i] = current[i];
            }
        }
        result = 1;
    } @catch (NSException *exception) {
        (void)exception;
        if (writesStarted) {
            // A native setter can fail after an earlier frame was written.
            // Roll back only still-current exact receivers, not stale views.
            for (unsigned i = 0; i < 3; i++) {
                @try {
                    if (candidates[i] && [_window standardWindowButton:(NSWindowButton)i] == candidates[i]
                        && candidates[i].window == _window && candidates[i].superview == parents[i])
                        candidates[i].frame = current[i];
                } @catch (NSException *rollbackException) { (void)rollbackException; }
            }
        }
        result = 0;
        VFDiagnosticReason = writesStarted ? 10 : 11;
    }
done:
    if(!result&&createdSupport) {[_support collapse];[_support release];_support=nil;}
    for (unsigned i = 0; i < 3; i++) {
        if (retained[i]) [candidates[i] release];
        if (parentsRetained[i]) [parents[i] release];
    }
    _status = result;
    _reconciling = NO;
    return result;
}

- (void)changed:(NSNotification *)notification {
    if (_closed || ![NSThread isMainThread] || notification.object != _window) return;
    [self reconcile];
}

- (void)willClose:(NSNotification *)notification {
    if (_closed || ![NSThread isMainThread] || notification.object != _window) return;
    _closingWindow = YES;
    [self close];
}

- (void)close {
    if (_closed) return;
    _closed = YES;
    _status = -1;
    // Remove even partially registered observations after initializer failure.
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    for (unsigned i = 0; i < 3; i++) {
        @try {
            if (!_closingWindow && _buttons[i] && [_window standardWindowButton:(NSWindowButton)i] == _buttons[i]
                && _buttons[i].window == _window && _buttons[i].superview
                && _buttons[i].superview == _parents[i]
                && VFValidRect(_originalFrames[i])
                && NSContainsRect(_buttons[i].superview.bounds, _originalFrames[i]))
                _buttons[i].frame = _originalFrames[i];
        } @catch (NSException *exception) { (void)exception; }
        [_buttons[i] release]; _buttons[i] = nil;
        [_parents[i] release]; _parents[i] = nil;
    }
    if(_support) {
        if(!_closingWindow)[_support collapse];
        [_support release];_support=nil;
    }
    // A native close is already mutating/compositing the window. Release only:
    // restoring inherited light chrome here could flash or disturb that close.
    if (!_closingWindow) {
        @try { _window.toolbar = _originalToolbar; } @catch (NSException *exception) { (void)exception; }
        @try { _window.appearance = _originalAppearance; } @catch (NSException *exception) { (void)exception; }
    }
    [_originalToolbar release]; _originalToolbar = nil;
    [_originalAppearance release]; _originalAppearance = nil;
    [_window release]; _window = nil;
}
- (void)dealloc { [self close]; [super dealloc]; }
@end

unsigned vf_window_controls_abi_version(void) { return 2; }
int vf_window_controls_diagnostic_reason(void) { return [NSThread isMainThread] ? VFDiagnosticReason : 1; }
double vf_window_controls_diagnostic_geometry(unsigned index) {
    return [NSThread isMainThread] && index < 40 ? VFDiagnosticGeometry[index] : NAN;
}

void *vf_window_controls_create(void *window, double xInset, double topInset) {
    if (![NSThread isMainThread]) return NULL;
    VFResetDiagnostic();
    if (!window || !isfinite(xInset) || !isfinite(topInset)
        || xInset < 0 || topInset < 0) { VFDiagnosticReason=2; return NULL; }
    @try {
        if (![(id)window isKindOfClass:[NSWindow class]]) { VFDiagnosticReason=2; return NULL; }
        return [[VFWindowControlsOwner alloc] initWithWindow:window horizontal:xInset top:topInset];
    } @catch (NSException *exception) { (void)exception; VFDiagnosticReason=11; return NULL; }
}

int vf_window_controls_reconcile(void *handle) {
    if (![NSThread isMainThread] || !handle) return -1;
    return [(VFWindowControlsOwner *)handle reconcile];
}

int vf_window_controls_status(void *handle) {
    if (![NSThread isMainThread] || !handle) return -1;
    return ((VFWindowControlsOwner *)handle)->_status;
}

int vf_window_controls_destroy(void **handle) {
    if (![NSThread isMainThread] || !handle) return 0;
    if (!*handle) return 1;
    VFWindowControlsOwner *owner = *handle;
    *handle = NULL;
    [owner close]; [owner release];
    return 1;
}
