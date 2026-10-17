// Public AppKit window controls. No Python callbacks, private frame access,
// delegate replacement, runtime compilation or fullscreen timing assumptions.
#import <AppKit/AppKit.h>
#include <math.h>

static BOOL VFValidRect(NSRect rect) {
    return isfinite(rect.origin.x) && isfinite(rect.origin.y)
        && isfinite(rect.size.width) && isfinite(rect.size.height)
        && isfinite(NSMaxX(rect)) && isfinite(NSMaxY(rect))
        && rect.size.width > 0 && rect.size.height > 0;
}

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
        if (!dark) { [self release]; return nil; }
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
        [self release];
        return nil;
    }
    return self;
}

- (int)reconcile {
    if (_closed || ![NSThread isMainThread]) return -1;
    if (_reconciling) return _status;
    _reconciling = YES;
    NSButton *candidates[3] = {nil, nil, nil};
    NSView *parents[3] = {nil, nil, nil};
    NSRect current[3], windowFrames[3], targets[3];
    BOOL retained[3] = {NO, NO, NO};
    BOOL parentsRetained[3] = {NO, NO, NO};
    BOOL writesStarted = NO;
    int result = 0;
    @try {
        NSView *content = _window.contentView;
        if (!content || content.window != _window || !VFValidRect(content.bounds)) goto done;
        NSRect contentWindow = [content convertRect:content.bounds toView:nil];
        if (!VFValidRect(contentWindow)) goto done;
        for (unsigned i = 0; i < 3; i++) {
            candidates[i] = [_window standardWindowButton:(NSWindowButton)i];
            if (!candidates[i] || candidates[i].window != _window) goto done;
            // AppKit may temporarily reparent or replace fullscreen controls.
            // Inspect only each current public button and its immediate view.
            parents[i] = candidates[i].superview;
            if (!parents[i] || parents[i].window != _window || !VFValidRect(parents[i].bounds)) goto done;
            current[i] = candidates[i].frame;
            if (!VFValidRect(current[i])) goto done;
            windowFrames[i] = [parents[i] convertRect:current[i] toView:nil];
            if (!VFValidRect(windowFrames[i])) goto done;
        }
        for (unsigned i = 0; i < 3; i++) {
            double x = NSMinX(contentWindow) + _horizontalInset
                + NSMinX(windowFrames[i]) - NSMinX(windowFrames[0]);
            double y = NSMaxY(contentWindow) - _topInset - windowFrames[i].size.height;
            NSRect windowTarget = NSMakeRect(x, y, windowFrames[i].size.width, windowFrames[i].size.height);
            if (!VFValidRect(windowTarget)) goto done;
            targets[i] = [parents[i] convertRect:windowTarget fromView:nil];
            if (!VFValidRect(targets[i]) || !NSContainsRect(parents[i].bounds, targets[i])) goto done;
        }
        // Retain replacements only after ALL current receivers and targets pass.
        for (unsigned i = 0; i < 3; i++) {
            [candidates[i] retain]; retained[i] = YES;
            [parents[i] retain]; parentsRetained[i] = YES;
        }
        // Revalidate identity after admission and before the first mutation.
        for (unsigned i = 0; i < 3; i++) {
            if ([_window standardWindowButton:(NSWindowButton)i] != candidates[i]
                || candidates[i].window != _window || candidates[i].superview != parents[i]) goto done;
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
    }
done:
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

unsigned vf_window_controls_abi_version(void) { return 1; }

void *vf_window_controls_create(void *window, double xInset, double topInset) {
    if (![NSThread isMainThread] || !window || !isfinite(xInset) || !isfinite(topInset)
        || xInset < 0 || topInset < 0) return NULL;
    @try {
        if (![(id)window isKindOfClass:[NSWindow class]]) return NULL;
        return [[VFWindowControlsOwner alloc] initWithWindow:window horizontal:xInset top:topInset];
    } @catch (NSException *exception) { (void)exception; return NULL; }
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
