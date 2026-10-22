#import <QuartzCore/QuartzCore.h>
// One Unified custom toolbar aperture carries the single Qt header.
// No original-content overlay, window delegate/control/body/presentation writes.
#import <AppKit/AppKit.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>

// Existing CPython entry points supplied by the interpreter. The callback
// entry below is compiled native code: no libffi executable closure or new
// hardened-runtime entitlement is required on x86_64.
typedef struct {
    uint32_t version,reserved;
    int (*ensure)(void);
    void (*release)(int);
    void (*incref)(void *);
    void (*decref)(void *);
    void *(*call)(void *);
    void (*clear)(void);
    int (*initialized)(void);
} VFHeaderPythonAPI;
static BOOL VFHeaderPythonAPIValid(const VFHeaderPythonAPI *api,size_t size) {
    return api&&size==sizeof(*api)&&api->version==1&&api->reserved==0
        &&api->ensure&&api->release&&api->incref&&api->decref
        &&api->call&&api->clear&&api->initialized;
}
@interface VFHeaderPythonContext : NSObject {
    VFHeaderPythonAPI _api;
    void *_callback;
}
- (instancetype)initWithCallback:(void *)callback api:(const VFHeaderPythonAPI *)api;
- (BOOL)invoke;
@end
@implementation VFHeaderPythonContext
- (instancetype)initWithCallback:(void *)callback api:(const VFHeaderPythonAPI *)api {
    self=[super init];if(!self)return nil;
    _api=*api;
    if(!callback||!_api.initialized()){[self release];return nil;}
    int state=_api.ensure();_api.incref(callback);_callback=callback;_api.release(state);
    return self;
}
- (BOOL)invoke {
    if(!_callback||!_api.initialized())return NO;
    int state=_api.ensure();void *result=_api.call(_callback);
    BOOL ok=result!=NULL;
    if(result)_api.decref(result);else _api.clear();
    _api.release(state);return ok;
}
- (void)dealloc {
    void *callback=_callback;_callback=NULL;
    if(callback&&_api.initialized&&_api.initialized()){
        int state=_api.ensure();_api.decref(callback);_api.release(state);
    }
    [super dealloc];
}
@end
static void VFHeaderInvokePython(void *context) {
    // The callback can clear/destroy its own host. Its active context stays
    // alive until the compiled invocation has returned through the C API.
    VFHeaderPythonContext *callback=[(VFHeaderPythonContext *)context retain];
    [callback invoke];[callback release];
}


typedef struct {
    uint64_t sequence,child;
    uint32_t kind,reserved;
    double x,y,timestamp;
} VFHeaderPointerSnapshot;

@class VFHeaderHost;
@class VFHeaderChildBinding;
static void VFHeaderHostWillRemoveSubview(VFHeaderHost *,NSView *);
static void VFHeaderLayoutChanged(VFHeaderHost *owner);
int vf_header_host_state(void *handle);
unsigned vf_header_host_flags(void *handle);
double vf_header_host_geometry(void *handle,unsigned index);
static char VFHeaderKVOContext;
static unsigned VFVisibleRect(NSView *view,NSRect *out);

@interface VFHeaderContainer : NSView {
@public
    NSUInteger _frameMutation;
    CGFloat _itemHeight;
    NSColor *_brandColor;
    VFHeaderHost *_owner;
    NSLayoutConstraint *_preferredWidth,*_heightConstraint;
}
@end
@implementation VFHeaderContainer
- (BOOL)isFlipped{return YES;}
- (void)drawRect:(NSRect)dirty {
    // AppKit's invalidation rectangle is not the view's drawing ownership.
    // A toolbar item must never cover the main window's content underneath it.
    NSRect paint=NSIntersectionRect(dirty,self.bounds);
    if(_brandColor&&!NSIsEmptyRect(paint)){[_brandColor setFill];NSRectFill(paint);}
}
- (void)setFrame:(NSRect)frame {
    _frameMutation++;@try{[super setFrame:frame];}@finally{_frameMutation--;}
    if(!_frameMutation)VFHeaderLayoutChanged(_owner);
}
- (void)setFrameOrigin:(NSPoint)origin {[super setFrameOrigin:origin];if(!_frameMutation)VFHeaderLayoutChanged(_owner);}
- (void)setFrameSize:(NSSize)size {[super setFrameSize:size];if(!_frameMutation)VFHeaderLayoutChanged(_owner);}
- (void)setBoundsSize:(NSSize)size {[super setBoundsSize:size];if(!_frameMutation)VFHeaderLayoutChanged(_owner);}
- (void)viewDidMoveToWindow {[super viewDidMoveToWindow];VFHeaderLayoutChanged(_owner);}
- (void)viewDidMoveToSuperview {[super viewDidMoveToSuperview];VFHeaderLayoutChanged(_owner);}
- (void)dealloc{_owner=nil;[_brandColor release];[_preferredWidth release];[_heightConstraint release];[super dealloc];}
- (NSSize)intrinsicContentSize{return NSMakeSize(NSViewNoIntrinsicMetric,NSViewNoIntrinsicMetric);}
- (void)resizeSubviewsWithOldSize:(NSSize)oldSize {
    (void)oldSize; // Qt child frame and inverse-container geometry have exact owners.
    if(!_frameMutation)VFHeaderLayoutChanged(_owner);
}
- (void)didAddSubview:(NSView *)view{[super didAddSubview:view];VFHeaderLayoutChanged(_owner);}
- (void)willRemoveSubview:(NSView *)view{VFHeaderHostWillRemoveSubview(_owner,view);[super willRemoveSubview:view];}
@end

#define VF_ITEM_VIEW_CLASS VFHeaderContainer
// Native Unified toolbar carrier; AppKit owns allocation, controls and material.
// AppKit owns the native controls, toolbar row, margins and material. This view
// owns only one item aperture. No window-content underlay claims that aperture
// owns native traffic-light pixels. No fullscreen policy/delegate changes.
#import <AppKit/AppKit.h>
#include <math.h>
#ifndef VF_TOOLBAR_CLASS
#define VF_TOOLBAR_CLASS NSToolbar
#endif
#ifndef VF_ITEM_VIEW_CLASS
#define VF_ITEM_VIEW_CLASS NSView
#endif
static NSString *const VFItemID=@"org.vodforge.qa.unified44.item";
@interface VF44Carrier : NSObject<NSToolbarDelegate> {
@public NSWindow *_window; id _windowDelegate; NSToolbar *_toolbar;
 NSToolbarItem *_item; NSView *_view; NSWindowToolbarStyle _oldStyle;
 NSLayoutConstraint *_heightConstraint,*_minimumWidthConstraint;
 BOOL _closed,_assigned,_styleWritten;
}
- (instancetype)initWithWindow:(NSWindow *)window minimumWidth:(CGFloat)minimum;
- (BOOL)current;
- (BOOL)close;
@end
@implementation VF44Carrier
- (instancetype)initWithWindow:(NSWindow *)window minimumWidth:(CGFloat)minimum {
 self=[super init];if(!self)return nil;
 if(!NSThread.isMainThread||!window||!isfinite(minimum)||minimum<=0||minimum>16384
    ||window.toolbar||window.titlebarAccessoryViewControllers.count
    ||!(window.styleMask&NSWindowStyleMaskFullSizeContentView)
    ||!window.titlebarAppearsTransparent||window.titleVisibility!=NSWindowTitleHidden){[self release];return nil;}
 _window=[window retain];_windowDelegate=[window.delegate retain];_oldStyle=window.toolbarStyle;
 @try {
  // Independent required height; width is measured/allocated by AppKit, never
  // fed back from the last window/host frame. No deprecated minSize/maxSize.
  _view=[[VF_ITEM_VIEW_CLASS alloc]initWithFrame:NSZeroRect];_view.translatesAutoresizingMaskIntoConstraints=NO;
  _heightConstraint=[[_view.heightAnchor constraintEqualToConstant:44]retain];_heightConstraint.active=YES;
  _minimumWidthConstraint=[[_view.widthAnchor constraintGreaterThanOrEqualToConstant:minimum]retain];_minimumWidthConstraint.active=YES;
  [_view setContentHuggingPriority:1 forOrientation:NSLayoutConstraintOrientationHorizontal];
  _item=[[NSToolbarItem alloc]initWithItemIdentifier:VFItemID];_item.view=_view;_item.label=@"VODForge";_item.bordered=NO;
  _item.visibilityPriority=NSToolbarItemVisibilityPriorityHigh;
  // Empty identifier avoids sharing customization state with another window.
  _toolbar=(NSToolbar *)[[VF_TOOLBAR_CLASS alloc]init];_toolbar.delegate=self;
  _toolbar.allowsUserCustomization=NO;_toolbar.autosavesConfiguration=NO;
  _toolbar.allowsExtensionItems=NO;_toolbar.displayMode=NSToolbarDisplayModeIconOnly;
  if([_toolbar respondsToSelector:@selector(setAllowsDisplayModeCustomization:)])_toolbar.allowsDisplayModeCustomization=NO;
  @try{window.toolbarStyle=NSWindowToolbarStyleUnified;}
  @finally{_styleWritten=window.toolbarStyle==NSWindowToolbarStyleUnified;}
  @try{window.toolbar=_toolbar;}
  @finally{_assigned=window.toolbar==_toolbar;}
  _toolbar.visible=YES;
  if(![self current]){[self close];[self release];return nil;}
 }@catch(NSException *error){(void)error;[self close];[self release];return nil;}
 return self;
}
- (NSArray *)toolbarAllowedItemIdentifiers:(NSToolbar *)toolbar{return toolbar==_toolbar?@[VFItemID]:@[];}
- (NSArray *)toolbarDefaultItemIdentifiers:(NSToolbar *)toolbar{return toolbar==_toolbar?@[VFItemID]:@[];}
- (NSToolbarItem *)toolbar:(NSToolbar *)toolbar itemForItemIdentifier:(NSToolbarItemIdentifier)identifier willBeInsertedIntoToolbar:(BOOL)inserted {
 (void)inserted;return !_closed&&toolbar==_toolbar&&[identifier isEqual:VFItemID]?_item:nil;
}
- (BOOL)current {
 return !_closed&&_assigned&&_styleWritten&&_window.toolbar==_toolbar&&_toolbar.delegate==self
 &&_item.view==_view&&_window.delegate==_windowDelegate&&_window.toolbarStyle==NSWindowToolbarStyleUnified
 &&_window.titlebarAccessoryViewControllers.count==0&&(_window.styleMask&NSWindowStyleMaskFullSizeContentView)
 &&_window.titlebarAppearsTransparent&&_window.titleVisibility==NSWindowTitleHidden;
}
- (BOOL)close {
 if(_closed)return YES;
 // Never remove a foreign toolbar or restore style after someone else changed
 // this exact generation. A refused close retains the carrier for inspection.
 if(_assigned&&![self current])return NO;
 @try {
  if(_assigned){_window.toolbar=nil;if(_window.toolbar)return NO;_assigned=NO;}
  if(_styleWritten){
   if(_window.toolbar||_window.delegate!=_windowDelegate||_window.toolbarStyle!=NSWindowToolbarStyleUnified)return NO;
   _window.toolbarStyle=_oldStyle;if(_window.toolbarStyle!=_oldStyle)return NO;_styleWritten=NO;
  }
 }@catch(NSException *error){(void)error;return NO;}
 if(_toolbar.delegate==self)_toolbar.delegate=nil;
 _closed=YES;return YES;
}
- (void)dealloc {
 // Caller must retain/refuse destruction if exact-generation close failed.
 [_heightConstraint release];[_minimumWidthConstraint release];[_view release];[_item release];
 [_toolbar release];[_windowDelegate release];[_window release];[super dealloc];
}
@end


// One exact public Qt child. Qt alone authors its frame; this binding owns only
// the inverse container and its event/lifetime bookkeeping.
@interface VFHeaderOffsetContainer:NSView {
@public VFHeaderChildBinding *_binding; // borrowed, cleared before release
}
@end
@interface VFHeaderChildBinding:NSObject {
@public VFHeaderHost *_owner; // borrowed; host retains binding
    NSView *_child,*_originalParent;
    VFHeaderOffsetContainer *_container;
    BOOL _closed,_mutating,_lost,_observing,_frameFlag,_boundsFlag,_frameWritten,_boundsWritten;
    NSRect _expected;
    NSTrackingArea *_pointerArea;
    VFHeaderPointerSnapshot _pointer;
}
- (instancetype)initWithOwner:(VFHeaderHost *)owner child:(NSView *)child rect:(NSRect)rect;
- (BOOL)current;
- (BOOL)fit;
- (BOOL)update:(NSRect)rect;
- (BOOL)unbind;
- (void)releaseOnly;
- (void)changed:(NSNotification *)notification;
- (void)layoutChanged;
- (void)willRemove:(NSView *)view;
- (BOOL)stopObserving:(BOOL)restore;
- (double)geometry:(unsigned)index;
- (void)recordPointer:(NSEvent *)event kind:(unsigned)kind;
- (void)stopPointerTracking;
@end

@interface VFHeaderHost : NSObject {
@public
    NSWindow *_window;
    VF44Carrier *_carrier;
    VFHeaderContainer *_view;
    VFHeaderChildBinding *_childBinding;
    id _windowDelegate;
    BOOL _closed,_closing,_nativeClosed;
    BOOL _layingOut,_layoutValid,_eventPending,_pipeFailed,_haveEventSnapshot;
    double _eventSnapshot[98],_eventRow[17];
    uintptr_t _eventButtonIDs[3];unsigned _eventFlags;int _eventStatus;
    int _eventRead,_eventWrite;
    double _gutter,_minWidth;
    NSButton *_observedButtons[3];
    BOOL _buttonFrameFlags[3],_buttonBoundsFlags[3],_buttonKVOHidden[3],_buttonKVOWindow[3],_buttonKVOAlpha[3];
    NSWindow *_buttonWindows[3];
    CGFloat _height;
    NSMapTable *_paintWindows;
    unsigned _transition;
    void (*_changeCallback)(void *);void *_changeContext;
    VFHeaderPythonContext *_pythonCallbackContext;
}
- (instancetype)initWithWindow:(NSWindow *)window height:(CGFloat)height gutter:(double)gutter minWidth:(double)minWidth;
- (void)layoutChanged;
- (void)changed:(NSNotification *)notification;
- (void)signal;
- (void)applyBrand;
- (void)refreshButtons;
- (void)stopButtons;
- (BOOL)current;
- (BOOL)ownedGeneration;
- (void)willClose:(NSNotification *)notification;
- (void)close;
@end
static BOOL VFChildFinite(NSRect r){return isfinite(r.origin.x)&&isfinite(r.origin.y)&&isfinite(r.size.width)&&isfinite(r.size.height)&&fabs(r.origin.x)<=16384&&fabs(r.origin.y)<=16384&&r.size.width>0&&r.size.height>0&&r.size.width<=16384&&r.size.height<=16384;}
static BOOL VFChildNear(NSRect a,NSRect b){return fabs(a.origin.x-b.origin.x)<.02&&fabs(a.origin.y-b.origin.y)<.02&&fabs(a.size.width-b.size.width)<.02&&fabs(a.size.height-b.size.height)<.02;}
@implementation VFHeaderOffsetContainer
- (BOOL)isFlipped{return YES;}
- (BOOL)isOpaque{return NO;}
- (void)setFrame:(NSRect)r{BOOL changed=!NSEqualRects(self.frame,r);[super setFrame:r];if(changed)[_binding layoutChanged];}
- (void)setBounds:(NSRect)r{BOOL changed=!NSEqualRects(self.bounds,r);[super setBounds:r];if(changed)[_binding layoutChanged];}
- (void)viewDidMoveToWindow{[super viewDidMoveToWindow];[_binding layoutChanged];}
- (void)viewDidMoveToSuperview{[super viewDidMoveToSuperview];[_binding layoutChanged];}
- (void)didAddSubview:(NSView *)view{[super didAddSubview:view];[_binding layoutChanged];}
- (void)willRemoveSubview:(NSView *)view{[_binding willRemove:view];[super willRemoveSubview:view];}
@end
@implementation VFHeaderChildBinding
- (instancetype)initWithOwner:(VFHeaderHost *)owner child:(NSView *)child rect:(NSRect)rect {
    self=[super init];if(!self)return nil;_owner=owner;_mutating=YES;
    _child=[child retain];_originalParent=[child.superview retain];
    _container=[[VFHeaderOffsetContainer alloc]initWithFrame:NSMakeRect(0,0,rect.size.width,rect.size.height)];
    if(_container)_container->_binding=self;_container.autoresizesSubviews=NO;
    // Install into the host only after the caller has shown/positioned its Qt
    // child normally. Constructor writes remain transactionally reachable.
    @try {
        [owner->_view addSubview:_container];[_container addSubview:child];
    } @catch(NSException *exception){(void)exception;_lost=YES;}
    _mutating=NO;
    if([self current]&&[self update:rect]) {
        @try {
            NSNotificationCenter *center=NSNotificationCenter.defaultCenter;
            _frameFlag=child.postsFrameChangedNotifications;_boundsFlag=child.postsBoundsChangedNotifications;
            _observing=YES; // cleanup covers each partial setter/registration
            _frameWritten=YES;child.postsFrameChangedNotifications=YES;
            _boundsWritten=YES;child.postsBoundsChangedNotifications=YES;
            _container.postsFrameChangedNotifications=YES;_container.postsBoundsChangedNotifications=YES;
            [center addObserver:self selector:@selector(changed:) name:NSViewFrameDidChangeNotification object:child];
            [center addObserver:self selector:@selector(changed:) name:NSViewBoundsDidChangeNotification object:child];
            [center addObserver:self selector:@selector(changed:) name:NSViewFrameDidChangeNotification object:_container];
            [center addObserver:self selector:@selector(changed:) name:NSViewBoundsDidChangeNotification object:_container];
            // Qt keeps the main QWindow as logical parent for correct global
            // and AX coordinates. In AppKit's fullscreen toolbar window Qt's
            // platform child-under-mouse filter can suppress its passive route.
            // Own only this exact child's standard AppKit tracking area; Qt
            // retains all button, drag, wheel, focus and gesture delivery.
            _pointerArea=[[NSTrackingArea alloc]initWithRect:NSZeroRect
                options:NSTrackingMouseMoved|NSTrackingMouseEnteredAndExited|NSTrackingInVisibleRect|NSTrackingActiveInActiveApp
                owner:self userInfo:nil];
            if(!_pointerArea)[NSException raise:@"pointer_tracking_unavailable" format:@"static"];
            [child addTrackingArea:_pointerArea];
        } @catch(NSException *exception){(void)exception;_lost=YES;}
    }
    return self; // host retains even a refused partial generation for cleanup
}
- (BOOL)current {
    return !_closed&&!_lost&&_owner&&!_owner->_nativeClosed&&[_owner current]
        &&_owner->_window.contentView==_originalParent&&_originalParent.window==_owner->_window
        &&_container.superview==_owner->_view&&_child.superview==_container
        &&_owner->_view.subviews.count==1&&_owner->_view.subviews[0]==_container
        &&_container.subviews.count==1&&_container.subviews[0]==_child
        &&_child.window&&_child.window==_owner->_view.window;
}
- (BOOL)fit {
    return [self current]&&VFChildNear(_child.frame,_expected)
        &&VFChildNear([_child convertRect:_child.bounds toView:_owner->_view],NSMakeRect(0,0,_expected.size.width,_expected.size.height));
}
- (BOOL)update:(NSRect)r {
    if(![self current]||!VFChildFinite(r)||!_child.isFlipped||!_owner->_view.isFlipped
        ||!VFChildNear(_child.frame,r)||!VFChildNear(_child.bounds,NSMakeRect(0,0,r.size.width,r.size.height)))return NO;
    NSRect bounds=NSMakeRect(fmin(0,r.origin.x),fmin(0,r.origin.y),r.size.width+fabs(r.origin.x),r.size.height+fabs(r.origin.y));
    NSRect frame=NSMakeRect(bounds.origin.x-r.origin.x,bounds.origin.y-r.origin.y,bounds.size.width,bounds.size.height);
    NSRect oldF=_container.frame,oldB=_container.bounds,oldExpected=_expected;BOOL ok=NO;_mutating=YES;
    @try {
        if(!NSEqualRects(_container.frame,frame))_container.frame=frame;
        if(!NSEqualRects(_container.bounds,bounds))_container.bounds=bounds;
        _expected=r;ok=[self fit];
        if(!ok&&[self current]){_container.frame=oldF;_container.bounds=oldB;_expected=oldExpected;}
    } @catch(NSException *exception) {
        (void)exception;
        @try{if([self current]){_container.frame=oldF;_container.bounds=oldB;_expected=oldExpected;}}@catch(NSException *ignored){(void)ignored;}
    }
    _mutating=NO;[_owner signal];return ok;
}
- (void)layoutChanged {if(!_closed&&!_mutating&&NSThread.isMainThread)[_owner signal];}
- (void)willRemove:(NSView *)view {
    if(!_closed&&!_mutating&&view==_child&&NSThread.isMainThread){_lost=YES;[_owner signal];}
}
- (void)changed:(NSNotification *)notification {
    if(notification.object==_child||notification.object==_container)[self layoutChanged];
}
- (void)stopPointerTracking {
    if(_pointerArea){[_child removeTrackingArea:_pointerArea];[_pointerArea release];_pointerArea=nil;}
    _pointer.kind=0;
}
- (void)recordPointer:(NSEvent *)event kind:(unsigned)kind {
    if(!NSThread.isMainThread||kind<1||kind>3||![self current]||![self fit]
        ||!_pointerArea||!_owner->_changeCallback||event.window!=_child.window||(kind!=3&&NSEvent.pressedMouseButtons))return;
    if((kind==1&&event.type!=NSEventTypeMouseEntered)||(kind==2&&event.type!=NSEventTypeMouseMoved)
        ||(kind==3&&event.type!=NSEventTypeMouseExited))return;
    NSPoint local=[_child convertPoint:event.locationInWindow fromView:nil];
    if(!isfinite(local.x)||!isfinite(local.y)||!isfinite(event.timestamp)||event.timestamp<0)return;
    if(kind!=3&&!NSPointInRect(local,_child.bounds))return;
    // Signal synchronously, keeping this binding/host alive if Python retires
    // the generation from inside the existing compiled callback.
    [[self retain]autorelease];VFHeaderHost *owner=[_owner retain];
    _pointer.sequence++;_pointer.child=(uintptr_t)_child;_pointer.kind=kind;
    _pointer.x=local.x;_pointer.y=local.y;_pointer.timestamp=event.timestamp;
    // Passive events use the already installed compiled main-thread callback,
    // not the geometry FD/dedup loop or another event queue.
    if(owner->_changeCallback)owner->_changeCallback(owner->_changeContext);
    [owner release];
}
- (void)mouseEntered:(NSEvent *)event {[self recordPointer:event kind:1];}
- (void)mouseMoved:(NSEvent *)event {[self recordPointer:event kind:2];}
- (void)mouseExited:(NSEvent *)event {[self recordPointer:event kind:3];}
- (BOOL)stopObserving:(BOOL)restore {
    [self stopPointerTracking];
    if(_observing){[NSNotificationCenter.defaultCenter removeObserver:self];_observing=NO;}
    // Retain failed flag-restoration intent for a same-generation cleanup retry.
    if(!restore){_frameWritten=NO;_boundsWritten=NO;return YES;}
    @try{if(_frameWritten){_child.postsFrameChangedNotifications=_frameFlag;if(_child.postsFrameChangedNotifications==_frameFlag)_frameWritten=NO;}}@catch(NSException *exception){(void)exception;}
    @try{if(_boundsWritten){_child.postsBoundsChangedNotifications=_boundsFlag;if(_child.postsBoundsChangedNotifications==_boundsFlag)_boundsWritten=NO;}}@catch(NSException *exception){(void)exception;}
    return !_frameWritten&&!_boundsWritten;
}
- (BOOL)unbind {
    if(_closed)return YES;if(!_owner)return NO;
    NSView *host=_owner->_view;
    BOOL hostCurrent=[_owner current]&&_container.superview==host&&host.subviews.count==1&&host.subviews[0]==_container;
    BOOL attached=hostCurrent&&_child.superview==_container&&_container.subviews.count==1&&_container.subviews[0]==_child;
    BOOL detached=hostCurrent&&_container.subviews.count==0&&(_child.superview==nil||(_child.superview==_originalParent&&_originalParent==_owner->_window.contentView));
    BOOL untouched=[_owner current]&&!_container.superview&&host.subviews.count==0
        &&_container.subviews.count==0&&_child.superview==_originalParent&&_originalParent==_owner->_window.contentView;
    if(!attached&&!detached&&!untouched)return NO;
    _mutating=YES;
    @try {
        if(![self stopObserving:attached||_child.superview==_originalParent]){_mutating=NO;return NO;}
        if(attached)[_child removeFromSuperview];
        if(_child.superview==_container||_container.subviews.count){_mutating=NO;return NO;}
        if(_container)_container->_binding=nil;[_container removeFromSuperview];_closed=YES;
    } @catch(NSException *exception){(void)exception;_mutating=NO;return NO;}
    _mutating=NO;return YES;
}
- (void)releaseOnly {
    if(_closed)return;[self stopObserving:NO];if(_container)_container->_binding=nil;_closed=YES;_owner=nil;
}
- (double)geometry:(unsigned)index {
    if(index>=32||![self current])return NAN;NSRect r;
    switch(index/4){
        case 0:r=_child.frame;break;case 1:r=_child.bounds;break;
        case 2:r=_container.frame;break;case 3:r=_container.bounds;break;
        case 4:r=[_child.window convertRectToScreen:[_child convertRect:_child.bounds toView:nil]];break;
        case 5:r=[_child convertRect:_child.bounds toView:_owner->_view];break;
        case 6:r=[_owner->_view.window convertRectToScreen:[_owner->_view convertRect:_owner->_view.bounds toView:nil]];break;
        default:r=[_owner->_window convertRectToScreen:[_originalParent convertRect:_originalParent.bounds toView:nil]];break;
    }
    double a[]={r.origin.x,r.origin.y,r.size.width,r.size.height};return a[index%4];
}
- (void)dealloc {
    [self stopObserving:NO];if(_container)_container->_binding=nil;
    [_container release];[_child release];[_originalParent release];[super dealloc];
}
@end

@implementation VFHeaderHost
- (instancetype)initWithWindow:(NSWindow *)window height:(CGFloat)height gutter:(double)gutter minWidth:(double)minWidth {
    self=[super init];if(!self)return nil;
    _eventRead=-1;_eventWrite=-1;
    _window=[window retain];_height=height;_gutter=gutter;_minWidth=minWidth;
    int descriptors[2];
    if(pipe(descriptors)!=0){[self release];return nil;}
    _eventRead=descriptors[0];_eventWrite=descriptors[1];
    for(unsigned i=0;i<2;i++) {
        if(fcntl(descriptors[i],F_SETFD,FD_CLOEXEC)==-1
            ||fcntl(descriptors[i],F_SETFL,fcntl(descriptors[i],F_GETFL)|O_NONBLOCK)==-1) {
            [self release];return nil;
        }
    }
    if(fcntl(_eventWrite,F_SETNOSIGPIPE,1)==-1){[self release];return nil;}
    @try {
        _windowDelegate=[window.delegate retain];
        _carrier=[[VF44Carrier alloc]initWithWindow:window minimumWidth:minWidth];
        if(!_carrier){[self release];return nil;}
        _view=(VFHeaderContainer *)[_carrier->_view retain];_view->_owner=self;
        _layoutValid=YES;
        if(![self current]){[self release];return nil;}
        NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
        for(NSNotificationName name in @[NSWindowDidResizeNotification,NSWindowDidMoveNotification,
            NSWindowWillEnterFullScreenNotification,NSWindowDidEnterFullScreenNotification,
            NSWindowWillExitFullScreenNotification,NSWindowDidExitFullScreenNotification,
            NSWindowDidChangeScreenNotification,NSWindowDidChangeBackingPropertiesNotification,
            NSWindowDidUpdateNotification,NSWindowDidChangeOcclusionStateNotification])
            [center addObserver:self selector:@selector(changed:) name:name object:window];
        [center addObserver:self selector:@selector(willClose:) name:NSWindowWillCloseNotification object:window];
        [self refreshButtons];[self layoutChanged];[self signal];
    } @catch(NSException *exception) {(void)exception;[self release];return nil;}
    return self;
}
- (BOOL)ownedGeneration {
    return _window&&_carrier&&_view&&[_carrier current]&&_carrier->_view==_view
        &&_window.delegate==_windowDelegate;
}
- (BOOL)current { return !_closed&&!_nativeClosed&&!_pipeFailed&&_layoutValid&&[self ownedGeneration]; }
- (void)signal {
    if(_closed||![NSThread isMainThread]||_eventWrite<0)return;
    // Window updates can be frequent. Wake Qt only for actual bounded state
    // changes, never a read->same setter->native update feedback loop.
    double snapshot[98];BOOL changed=!_haveEventSnapshot;
    unsigned flags=vf_header_host_flags(self);int status=vf_header_host_state(self);
    if(flags!=_eventFlags||status!=_eventStatus)changed=YES;
    for(unsigned i=0;i<98;i++) {
        snapshot[i]=vf_header_host_geometry(self,i);
        if(!((isnan(snapshot[i])&&isnan(_eventSnapshot[i]))||snapshot[i]==_eventSnapshot[i]))changed=YES;
    }
    // Per-button visibility and lifecycle are part of the transaction too.
    // A minimize/zoom-only visibility change must wake Qt even when the close
    // button, all full bounds and toolbar-era flags remain unchanged.
    double row[17]={0};row[0]=_transition;NSRect clip;
    row[1]=VFVisibleRect(_view,&clip);
    uintptr_t identities[3];
    for(unsigned i=0;i<3;i++) {
        NSButton *button=[_window standardWindowButton:(NSWindowButton)i];
        identities[i]=(uintptr_t)button;
        row[2+i*5]=VFVisibleRect(button,&clip);
        row[3+i*5]=clip.origin.x;row[4+i*5]=clip.origin.y;
        row[5+i*5]=clip.size.width;row[6+i*5]=clip.size.height;
        if(identities[i]!=_eventButtonIDs[i])changed=YES;
    }
    for(unsigned i=0;i<17;i++)if(row[i]!=_eventRow[i])changed=YES;
    if(!changed)return;
    for(unsigned i=0;i<17;i++)_eventRow[i]=row[i];
    for(unsigned i=0;i<3;i++)_eventButtonIDs[i]=identities[i];
    for(unsigned i=0;i<98;i++)_eventSnapshot[i]=snapshot[i];
    _eventFlags=flags;_eventStatus=status;_haveEventSnapshot=YES;
    if(!_eventPending){
    unsigned char byte=1;ssize_t result;
    do{result=write(_eventWrite,&byte,1);}while(result<0&&errno==EINTR);
    if(result==1||(result<0&&(errno==EAGAIN||errno==EWOULDBLOCK)))_eventPending=YES;
    else if(result<0&&errno!=EINTR)_pipeFailed=YES;
    }
    // Same-main-thread layout delivery precedes drawing; FD remains a wake-up
    // fallback, not the sole owner of a later corrective inset/width update.
    if(_changeCallback){
        void (*callback)(void *)=_changeCallback;void *context=_changeContext;
        // A synchronous Qt refusal may retire this exact host from inside the
        // callback. Keep its native stack owner alive until callback return.
        // Native notifications can call signal more than once on their stack.
        // Standard autorelease lifetime also protects those outer callers.
        [[self retain]autorelease];callback(context);
    }
}
- (void)stopButtons {
    NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
    for(unsigned i=0;i<3;i++)if(_observedButtons[i]) {
        NSButton *button=_observedButtons[i];
        if(_buttonKVOHidden[i]){@try{[button removeObserver:self forKeyPath:@"hidden" context:&VFHeaderKVOContext];}@catch(NSException *e){(void)e;}_buttonKVOHidden[i]=NO;}
        if(_buttonKVOAlpha[i]){@try{[button removeObserver:self forKeyPath:@"alphaValue" context:&VFHeaderKVOContext];}@catch(NSException *e){(void)e;}_buttonKVOAlpha[i]=NO;}
        if(_buttonKVOWindow[i]){@try{[button removeObserver:self forKeyPath:@"window" context:&VFHeaderKVOContext];}@catch(NSException *e){(void)e;}_buttonKVOWindow[i]=NO;}
        [center removeObserver:self name:NSViewFrameDidChangeNotification object:button];
        [center removeObserver:self name:NSViewBoundsDidChangeNotification object:button];
        if(!_nativeClosed&&[_window standardWindowButton:(NSWindowButton)i]==button) {
            button.postsFrameChangedNotifications=_buttonFrameFlags[i];
            button.postsBoundsChangedNotifications=_buttonBoundsFlags[i];
        }
        if(_buttonWindows[i]&&_buttonWindows[i]!=_window) {
            [center removeObserver:self name:NSWindowDidUpdateNotification object:_buttonWindows[i]];
            [center removeObserver:self name:NSWindowDidChangeOcclusionStateNotification object:_buttonWindows[i]];
        }
        [_buttonWindows[i] release];_buttonWindows[i]=nil;
        [button release];_observedButtons[i]=nil;
    }
}
- (void)refreshButtons {
    if(_closed||_nativeClosed||![NSThread isMainThread])return;
    BOOL unchanged=YES;
    for(unsigned i=0;i<3;i++) {
        NSButton *button=[_window standardWindowButton:(NSWindowButton)i];
        if(button!=_observedButtons[i]||(button&&button.window!=_buttonWindows[i])){unchanged=NO;break;}
    }
    if(unchanged)return;
    [self stopButtons];
    NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
    for(unsigned i=0;i<3;i++) {
        NSButton *button=[_window standardWindowButton:(NSWindowButton)i];if(!button)continue;
        _observedButtons[i]=[button retain];_buttonWindows[i]=[button.window retain];
        _buttonFrameFlags[i]=button.postsFrameChangedNotifications;
        _buttonBoundsFlags[i]=button.postsBoundsChangedNotifications;
        // Enable notifications only on this exact app's current real view.
        // Cleanup restores that view's captured flags even after native transfer;
        // no control frame/support geometry is ever changed.
        if(button.window==_window) {
            button.postsFrameChangedNotifications=YES;button.postsBoundsChangedNotifications=YES;
            [center addObserver:self selector:@selector(changed:) name:NSViewFrameDidChangeNotification object:button];
            [center addObserver:self selector:@selector(changed:) name:NSViewBoundsDidChangeNotification object:button];
        }
        @try{[button addObserver:self forKeyPath:@"hidden" options:0 context:&VFHeaderKVOContext];_buttonKVOHidden[i]=YES;}@catch(NSException *e){(void)e;}
        @try{[button addObserver:self forKeyPath:@"alphaValue" options:0 context:&VFHeaderKVOContext];_buttonKVOAlpha[i]=YES;}@catch(NSException *e){(void)e;}
        @try{[button addObserver:self forKeyPath:@"window" options:0 context:&VFHeaderKVOContext];_buttonKVOWindow[i]=YES;}@catch(NSException *e){(void)e;}
        if(button.window&&button.window!=_window) {
            [center addObserver:self selector:@selector(changed:) name:NSWindowDidUpdateNotification object:button.window];
            [center addObserver:self selector:@selector(changed:) name:NSWindowDidChangeOcclusionStateNotification object:button.window];
        }
    }
}
- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
    (void)keyPath;(void)change;
    if(context!=&VFHeaderKVOContext)return;
    if(_closed||_nativeClosed||![NSThread isMainThread])return;
    for(unsigned i=0;i<3;i++)if(object==_observedButtons[i]){[self layoutChanged];[self signal];return;}
}
- (void)changed:(NSNotification *)notification {
    if(_closed||_nativeClosed||![NSThread isMainThread])return;
    BOOL owned=notification.object==_window;
    for(unsigned i=0;i<3;i++)if(notification.object==_observedButtons[i]||notification.object==_buttonWindows[i])owned=YES;
    if(!owned)return;
    if([notification.name isEqual:NSWindowWillEnterFullScreenNotification])_transition=1;
    if([notification.name isEqual:NSWindowWillExitFullScreenNotification])_transition=2;
    if([notification.name isEqual:NSWindowDidEnterFullScreenNotification]||[notification.name isEqual:NSWindowDidExitFullScreenNotification])_transition=0;
    [self refreshButtons];[self layoutChanged];[self signal];
}
- (void)applyBrand {
    if(!_view->_brandColor||![_carrier current])return;
    NSWindow *window=_view.window;
    if(!window||!_paintWindows)return;
    if(![_paintWindows objectForKey:window]){
        [_paintWindows setObject:window.backgroundColor?:NSColor.clearColor forKey:window];
        window.backgroundColor=_view->_brandColor;
    }
}
- (void)layoutChanged {
    if(_closed||_nativeClosed||_layingOut||!NSThread.isMainThread||!_view)return;
    _layingOut=YES;[self applyBrand];
    // A pending AppKit allocation is observable, never repaired with an offset.
    _layoutValid=isfinite(_height)&&_height>0&&_height<=256;
    _layingOut=NO;[self signal];
}
- (void)willClose:(NSNotification *)notification {
    if(![NSThread isMainThread]||notification.object!=_window||_closed)return;
    _closing=YES;_nativeClosed=YES;[self signal];
}
- (void)close {
    if(_closed)return;_changeCallback=NULL;_changeContext=NULL;_closed=YES;
    [_pythonCallbackContext release];_pythonCallbackContext=nil;
    if(_childBinding){[_childBinding releaseOnly];[_childBinding release];_childBinding=nil;}
    if(_view)_view->_owner=nil;[self stopButtons];
    for(NSWindow *window in _paintWindows.keyEnumerator){
        if([window.backgroundColor isEqual:_view->_brandColor])window.backgroundColor=[_paintWindows objectForKey:window];
    }
    [_paintWindows removeAllObjects];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    // Restore only this exact current toolbar generation. A closing native
    // window need not be restyled. Never touch a foreign toolbar/delegate.
    @try {
        if(!_nativeClosed&&[_carrier current])[_carrier close];
        if(_carrier&&_carrier->_toolbar.delegate==_carrier)_carrier->_toolbar.delegate=nil;
    } @catch(NSException *exception){(void)exception;}
    [_view release];_view=nil;[_carrier release];_carrier=nil;
    [_windowDelegate release];_windowDelegate=nil;
    [_window release];_window=nil;
    if(_eventRead>=0){close(_eventRead);_eventRead=-1;}
    if(_eventWrite>=0){close(_eventWrite);_eventWrite=-1;}
}
- (void)dealloc{[self close];[_paintWindows release];[super dealloc];}
@end
unsigned vf_header_host_abi_version(void){return 6;}
void *vf_header_host_create(void *window,double height,double gutter,double minWidth) {
    if(![NSThread isMainThread]||!window||!isfinite(height)||height!=44
        ||!isfinite(gutter)||gutter<0||gutter>256||!isfinite(minWidth)||minWidth<=0||minWidth>16384)return NULL;
    @try {
        if(![(id)window isKindOfClass:[NSWindow class]])return NULL;
        // An existing exact native owner may still be retiring a Qt child.
        // Never nest hosts or steal its toolbar before that owner releases it.
        NSWindow *w=window;
        if(w.toolbar||w.titlebarAccessoryViewControllers.count||!w.titlebarAppearsTransparent
            ||w.titleVisibility!=NSWindowTitleHidden)return NULL;
        // Body remains full-size; ownership never enables flags after creation.
        if(!([(NSWindow *)window styleMask]&NSWindowStyleMaskFullSizeContentView))return NULL;
        return [[VFHeaderHost alloc] initWithWindow:window height:height gutter:gutter minWidth:minWidth];
    } @catch(NSException *exception){(void)exception;return NULL;}
}
int vf_header_host_state(void *handle) {
    if(![NSThread isMainThread]||!handle)return -1;
    VFHeaderHost *host=handle;if(host->_closed||host->_nativeClosed)return -1;
    @try{return [host current]?1:0;}@catch(NSException *exception){(void)exception;return 0;}
}
void *vf_header_host_view(void *handle) {
    return vf_header_host_state(handle)==1?((VFHeaderHost *)handle)->_view:NULL;
}
double vf_header_host_geometry(void *handle,unsigned index) {
    if(vf_header_host_state(handle)!=1||index>=98)return NAN;
    VFHeaderHost *h=handle;
    @try {
        if(index>=66)return h->_childBinding?[h->_childBinding geometry:index-66]:NAN;
        NSRect rects[5]={h->_window.contentView.bounds,h->_window.contentLayoutRect,
            h->_view.bounds,[h->_view convertRect:h->_view.bounds toView:nil],h->_window.frame};
        if(index<20){NSRect r=rects[index/4];double v[4]={r.origin.x,r.origin.y,r.size.width,r.size.height};return v[index%4];}
        if(index==20)return h->_height;
        if(index==21)return h->_window.styleMask;
        if(index==22)return h->_carrier->_toolbar.visible;
        if(index==23)return h->_window.delegate==h->_windowDelegate;
        if(index>=62) {
            NSView *content=h->_window.contentView;
            NSRect r=[h->_window convertRectToScreen:[content convertRect:content.bounds toView:nil]];
            double v[4]={r.origin.x,r.origin.y,r.size.width,r.size.height};return v[index-62];
        }
        if(index>=27&&index<31) {
            NSWindow *hostWindow=h->_view.window;if(!hostWindow)return NAN;
            NSRect r=[hostWindow convertRectToScreen:[h->_view convertRect:h->_view.bounds toView:nil]];
            double v[4]={r.origin.x,r.origin.y,r.size.width,r.size.height};return v[index-27];
        }
        if(index>=31&&index<61) {
            unsigned which=(index-31)/10,field=(index-31)%10;
            NSButton *button=[h->_window standardWindowButton:(NSWindowButton)which];
            if(field==0)return button&&button.window?1:0;
            if(!button||!button.window)return NAN;
            if(field==1)return button.window==h->_window;
            NSRect r=[button convertRect:button.bounds toView:nil];
            if(field>=6)r=[button.window convertRectToScreen:r];
            double v[4]={r.origin.x,r.origin.y,r.size.width,r.size.height};return v[(field-2)%4];
        }
        if(!NSApp)return NAN; // Read only; never create/activate an application.
        if(index==24)return NSApp.presentationOptions;
        if(index==25)return NSApp.currentSystemPresentationOptions;
        if(index==26)return [NSMenu menuBarVisible];
        return NSWorkspace.sharedWorkspace.accessibilityDisplayShouldReduceMotion;
    } @catch(NSException *exception){(void)exception;return NAN;}
}
int vf_header_host_destroy(void **handle) {
    if(![NSThread isMainThread]||!handle)return 0;if(!*handle)return 1;
    VFHeaderHost *host=*handle;
    // The caller must retire its Qt native child while its foreign parent is
    // still assigned. Keep this owner/FD alive if that public detach did not
    // complete; releasing underneath a live QNSView risks stale Qt callbacks.
    if(host->_childBinding&&!host->_nativeClosed)return 0;
    if(!host->_nativeClosed&&host->_view&&host->_view.subviews.count)return 0;
    if(!host->_nativeClosed&&![host ownedGeneration])return 0;
    *handle=NULL;[host close];[host release];return 1;
}

static void VFHeaderLayoutChanged(VFHeaderHost *owner){if(owner)[owner layoutChanged];}
int vf_header_host_event_fd(void *handle) {
    if(![NSThread isMainThread]||!handle)return -1;
    VFHeaderHost *host=handle;return host->_closed?-1:host->_eventRead;
}
int vf_header_host_drain(void *handle) {
    if(![NSThread isMainThread]||!handle)return -1;
    VFHeaderHost *host=handle;if(host->_closed||host->_eventRead<0||host->_pipeFailed)return -1;
    unsigned char bytes[64];int count=0;ssize_t n;
    for(;;) {
        n=read(host->_eventRead,bytes,sizeof bytes);
        if(n>0){count+=(int)n;continue;}
        if(n<0&&errno==EINTR)continue;
        break;
    }
    if(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK)return -1;
    host->_eventPending=NO;return count;
}
unsigned vf_header_host_flags(void *handle) {
    if(![NSThread isMainThread]||!handle)return 0;
    VFHeaderHost *h=handle;if(h->_closed||h->_nativeClosed)return 0;
    unsigned flags=0;
    @try {
        if([h current])flags|=1;if(h->_view.window)flags|=2;if(h->_carrier->_toolbar.visible)flags|=4;
        if(h->_window.delegate==h->_windowDelegate)flags|=8;
        if(h->_window.styleMask&NSWindowStyleMaskFullScreen)flags|=16;
        NSButton *b=[h->_window standardWindowButton:NSWindowCloseButton];
        if(b&&b.window) {
            NSRect clip;unsigned visibility=VFVisibleRect(b,&clip);
            if(visibility==2)flags|=128;
            else if(visibility==1)flags|=32;
        }
        if(h->_layoutValid)flags|=64;
        if(h->_childBinding){flags|=256;if([h->_childBinding current])flags|=512;if([h->_childBinding fit])flags|=1024;}
    } @catch(NSException *exception){(void)exception;}
    return flags;
}

int vf_header_host_set_height(void *handle,double height) {
    // This bounded source check has one independent44-point design policy.
    return vf_header_host_state(handle)==1&&isfinite(height)&&height==44;
}

static void VFHeaderHostWillRemoveSubview(VFHeaderHost *owner,NSView *view) {
    if(!owner||owner->_closed||owner->_nativeClosed||!NSThread.isMainThread)return;
    VFHeaderChildBinding *b=owner->_childBinding;
    if(b&&view==b->_container&&!b->_mutating){b->_lost=YES;[owner signal];}
}
int vf_header_host_bind_child(void *handle,void *child,double x,double y,double w,double h) {
    if(vf_header_host_state(handle)!=1||!child)return 0;VFHeaderHost *owner=handle;
    NSView *view=child;NSRect r=NSMakeRect(x,y,w,h);
    @try {
        if(owner->_childBinding||![view isKindOfClass:NSView.class]||!VFChildFinite(r)
            ||view==owner->_view||view.window!=owner->_window||view.superview!=owner->_window.contentView
            ||owner->_view.subviews.count||!view.isFlipped||!owner->_view.isFlipped
            ||!VFChildNear(view.frame,r)||!VFChildNear(view.bounds,NSMakeRect(0,0,w,h)))return 0;
        owner->_childBinding=[[VFHeaderChildBinding alloc]initWithOwner:owner child:view rect:r];
        if(!owner->_childBinding)return 0;
        if([owner->_childBinding current]&&[owner->_childBinding fit]){[owner signal];return 1;}
        if([owner->_childBinding unbind]){[owner->_childBinding release];owner->_childBinding=nil;}
        [owner signal];return 0;
    } @catch(NSException *exception){(void)exception;[owner signal];return 0;}
}
// Additive passive-input ABI. A snapshot is never a stored event queue: the
// synchronous callback consumes it once and stale/retired generations refuse.
size_t vf_header_host_pointer_snapshot_size(void){return sizeof(VFHeaderPointerSnapshot);}
int vf_header_host_pointer_snapshot(void *handle,VFHeaderPointerSnapshot *out) {
    if(!NSThread.isMainThread||!handle||!out)return -1;
    VFHeaderHost *owner=handle;VFHeaderChildBinding *b=owner->_childBinding;
    if(!b||![b current]||![b fit])return -1;
    if(!b->_pointer.kind)return 0;
    *out=b->_pointer;return 1;
}
int vf_header_host_update_child(void *handle,void *child,double x,double y,double w,double h) {
    if(vf_header_host_state(handle)!=1||!child)return 0;VFHeaderHost *owner=handle;
    @try{return owner->_childBinding&&owner->_childBinding->_child==(NSView *)child
        ?[owner->_childBinding update:NSMakeRect(x,y,w,h)]:0;}
    @catch(NSException *exception){(void)exception;return 0;}
}
int vf_header_host_unbind_child(void *handle,void *child) {
    if(!NSThread.isMainThread||!handle||!child)return 0;VFHeaderHost *owner=handle;
    @try {
        if(owner->_closed||!owner->_childBinding||owner->_childBinding->_child!=(NSView *)child)return 0;
        if(owner->_nativeClosed)[owner->_childBinding releaseOnly];
        else if(![owner->_childBinding unbind])return 0;
        [owner->_childBinding release];owner->_childBinding=nil;[owner signal];return 1;
    } @catch(NSException *exception){(void)exception;return 0;}
}

// One ABI6 packet; no Python sequence of separately-changing native getters.
typedef struct {
    uint32_t abi,flags,transition,reserved;
    uint64_t hostIdentity,accessoryIdentity,delegateIdentity,buttonIdentities[3];
    double geometry[98],visibleControls[12];
    uint32_t visibility[3],hostVisible;
} VFHeaderRowSnapshot;
static unsigned VFVisibleRect(NSView *view,NSRect *out) {
    *out=NSZeroRect;
    if(!view||!view.window)return 0;
    if(view.hiddenOrHasHiddenAncestor||!view.window.visible||view.window.alphaValue==0)return 2;
    // Fullscreen AppKit retains the genuine buttons and their positive frames
    // in an overlay window, but fades each button to alpha zero. Existence,
    // hidden flags and visibleRect alone therefore do not mean painted controls.
    // Read the public presentation value when present so a fade-out keeps its
    // clearance until its last positive-opacity frame. No threshold, pointer
    // inference, previous-state latch, frame setter or second animation.
    unsigned depth=0;
    for(NSView *ancestor=view;ancestor;ancestor=ancestor.superview){
        if(++depth>64)return 0;
        CALayer *layer=ancestor.layer,*presentation=layer.presentationLayer;
        double alpha=presentation?presentation.opacity:ancestor.alphaValue;
        if(!isfinite(alpha)||alpha<0||alpha>1)return 0;
        if(alpha==0)return 2;
        if(layer&&!presentation){
            if(!isfinite(layer.opacity)||layer.opacity<0||layer.opacity>1)return 0;
            if(layer.hidden||layer.opacity==0)return 2;
        }else if(presentation&&presentation.hidden)return 2;
    }
    NSRect local=NSIntersectionRect(view.bounds,view.visibleRect);
    if(NSIsEmptyRect(local))return 2;
    NSRect full=[view.window convertRectToScreen:[view convertRect:local toView:nil]],clip=NSZeroRect;
    for(NSScreen *screen in NSScreen.screens){
        NSRect part=NSIntersectionRect(full,screen.frame);
        if(NSIsEmptyRect(part))continue;
        if(!NSIsEmptyRect(clip)&&!NSEqualRects(clip,part))return 0;
        clip=part;
    }
    if(NSIsEmptyRect(clip))return 2;*out=clip;return 1;
}
size_t vf_header_host_row_snapshot_size(void){return sizeof(VFHeaderRowSnapshot);}
int vf_header_host_row_snapshot(void *handle,VFHeaderRowSnapshot *out) {
    if(!out||vf_header_host_state(handle)!=1)return 0;
    VFHeaderHost *h=handle;VFHeaderRowSnapshot s={0};s.abi=6;
    @try {
        s.flags=vf_header_host_flags(handle);s.transition=h->_transition;
        s.hostIdentity=(uint64_t)(uintptr_t)h->_view;
        s.accessoryIdentity=(uint64_t)(uintptr_t)h->_carrier->_toolbar;
        s.delegateIdentity=(uint64_t)(uintptr_t)h->_windowDelegate;
        for(unsigned i=0;i<98;i++)s.geometry[i]=vf_header_host_geometry(handle,i);
        NSRect visible;s.hostVisible=VFVisibleRect(h->_view,&visible)==1;
        for(unsigned i=0;i<3;i++){
            NSButton *button=[h->_window standardWindowButton:(NSWindowButton)i];
            s.buttonIdentities[i]=(uint64_t)(uintptr_t)button;
            s.visibility[i]=VFVisibleRect(button,&visible);
            double v[]={visible.origin.x,visible.origin.y,visible.size.width,visible.size.height};
            for(unsigned j=0;j<4;j++)s.visibleControls[i*4+j]=v[j];
        }
        if(![h current])return 0;*out=s;return 1;
    }@catch(NSException *exception){(void)exception;return 0;}
}

// Register/retire only the exact live generation, on its main thread.
int vf_header_host_set_change_callback(void *handle,void (*callback)(void *),void *context) {
    if(!NSThread.isMainThread||!handle)return 0;VFHeaderHost *h=handle;
    if(h->_closed)return 0;
    VFHeaderPythonContext *old=h->_pythonCallbackContext;h->_pythonCallbackContext=nil;
    h->_changeCallback=callback;h->_changeContext=callback?context:NULL;
    [old release];return 1;
}

size_t vf_header_host_python_api_size(void){return sizeof(VFHeaderPythonAPI);}
int vf_header_host_set_python_callback(void *handle,void *callback,
                                      const VFHeaderPythonAPI *api,size_t size) {
    if(!NSThread.isMainThread||!handle||!VFHeaderPythonAPIValid(api,size))return 0;
    VFHeaderHost *h=handle;if(h->_closed)return 0;
    VFHeaderPythonContext *context=callback?[[VFHeaderPythonContext alloc]initWithCallback:callback api:api]:nil;
    if(callback&&!context)return 0;
    VFHeaderPythonContext *old=h->_pythonCallbackContext;
    h->_pythonCallbackContext=context;
    h->_changeCallback=context?VFHeaderInvokePython:NULL;h->_changeContext=context;
    [old release];return 1;
}
int vf_header_host_python_callback_smoke(void *callback,const VFHeaderPythonAPI *api,size_t size) {
    if(!callback||!VFHeaderPythonAPIValid(api,size))return 0;
    VFHeaderPythonContext *context=[[VFHeaderPythonContext alloc]initWithCallback:callback api:api];
    if(!context)return 0;BOOL ok=[context invoke];[context release];return ok?1:0;
}

int vf_header_host_set_background(void *handle,double red,double green,double blue,double alpha){
    if(vf_header_host_state(handle)!=1||!isfinite(red)||!isfinite(green)||!isfinite(blue)||!isfinite(alpha)
       ||red<0||red>1||green<0||green>1||blue<0||blue>1||alpha!=1)return 0;
    VFHeaderHost *h=handle;NSColor *color=[NSColor colorWithSRGBRed:red green:green blue:blue alpha:alpha];
    if([h->_view->_brandColor isEqual:color])return 1;
    if(!h->_paintWindows)h->_paintWindows=[[NSMapTable weakToStrongObjectsMapTable]retain];
    for(NSWindow *window in h->_paintWindows.keyEnumerator)
        if([window.backgroundColor isEqual:h->_view->_brandColor])window.backgroundColor=color;
    [h->_view->_brandColor release];h->_view->_brandColor=[color retain];
    [h applyBrand];[h->_view setNeedsDisplay:YES];return 1;
}

// Optional QA-only numeric observation. ABI6 and runtime snapshots stay unchanged.
// Rows: host, close, minimize, zoom. No identities or user content leave native code.
// Each row: window/view/model/presentation opacity, then model/presentation
// layer frames, then minimum effective opacity across the ancestor chain.
// This minimum is diagnostic (not composited pixel alpha). Frames are in their respective superlayer coordinates. Missing layer => NaN.
int vf_header_host_qa_presentation(void *handle,double *out,size_t count) {
    if(!NSThread.isMainThread||!handle||!out||count!=52)return 0;
    VFHeaderHost *h=handle;
    if(![h current])return 0;
    double values[52];for(unsigned i=0;i<52;i++)values[i]=NAN;
    @try {
        NSView *views[4]={h->_view,
            [h->_window standardWindowButton:NSWindowCloseButton],
            [h->_window standardWindowButton:NSWindowMiniaturizeButton],
            [h->_window standardWindowButton:NSWindowZoomButton]};
        for(unsigned i=0;i<4;i++) {
            NSView *view=views[i];if(!view||!view.window)continue;
            CALayer *model=view.layer,*presentation=model.presentationLayer;
            unsigned k=i*13;
            double minimum=view.window.alphaValue;unsigned depth=0;
            for(NSView *ancestor=view;ancestor;ancestor=ancestor.superview){
                if(++depth>64){minimum=NAN;break;}
                CALayer *layer=ancestor.layer,*shown=layer.presentationLayer;
                double alpha=shown?shown.opacity:ancestor.alphaValue;
                if(!isfinite(alpha)||alpha<0||alpha>1){minimum=NAN;break;}
                if(ancestor.hidden||(shown&&shown.hidden))alpha=0;
                if(layer&&!shown){
                    if(!isfinite(layer.opacity)||layer.opacity<0||layer.opacity>1){minimum=NAN;break;}
                    alpha=fmin(alpha,layer.hidden?0:layer.opacity);
                }
                minimum=fmin(minimum,alpha);
            }
            values[k+12]=minimum;
            values[k]=view.window.alphaValue;values[k+1]=view.alphaValue;
            if(model){
                values[k+2]=model.opacity;CGRect r=model.frame;
                values[k+4]=r.origin.x;values[k+5]=r.origin.y;
                values[k+6]=r.size.width;values[k+7]=r.size.height;
            }
            if(presentation){
                values[k+3]=presentation.opacity;CGRect r=presentation.frame;
                values[k+8]=r.origin.x;values[k+9]=r.origin.y;
                values[k+10]=r.size.width;values[k+11]=r.size.height;
            }
        }
        if(![h current])return 0;
        for(unsigned i=0;i<52;i++)out[i]=values[i];return 1;
    }@catch(NSException *exception){(void)exception;return 0;}
}
