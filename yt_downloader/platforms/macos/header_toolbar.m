// Public event-driven custom-view toolbar hosting the real Qt header. No window-delegate,
// controls/support-frame, presentation-options, or body-layout mutation.
#import <AppKit/AppKit.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#ifndef VF_HEADER_TOOLBAR_CLASS
#define VF_HEADER_TOOLBAR_CLASS NSToolbar
#endif

@class VFHeaderHost;
@class VFHeaderChildBinding;
static void VFHeaderHostWillRemoveSubview(VFHeaderHost *,NSView *);
static void VFHeaderLayoutChanged(VFHeaderHost *owner);
int vf_header_host_state(void *handle);
unsigned vf_header_host_flags(void *handle);
double vf_header_host_geometry(void *handle,unsigned index);
static char VFHeaderKVOContext;
static NSString * const VFHeaderItemID=@"org.vodforge.qa.integrated-header";
@interface VFHeaderContainer : NSView {
@public
    CGFloat _itemHeight;
    VFHeaderHost *_owner;
    NSLayoutConstraint *_preferredWidth,*_heightConstraint;
}
- (instancetype)initWithHeight:(CGFloat)height;
@end
@implementation VFHeaderContainer
- (instancetype)initWithHeight:(CGFloat)height {
    self=[super initWithFrame:NSMakeRect(0,0,1,height)];if(!self)return nil;
    _itemHeight=height;self.autoresizesSubviews=YES;
    self.translatesAutoresizingMaskIntoConstraints=NO;
    _heightConstraint=[[self.heightAnchor constraintEqualToConstant:height] retain];_heightConstraint.active=YES;
    _preferredWidth=[[self.widthAnchor constraintEqualToConstant:1] retain];
    _preferredWidth.priority=NSLayoutPriorityDefaultHigh;_preferredWidth.active=YES;
    [self setContentHuggingPriority:1 forOrientation:NSLayoutConstraintOrientationHorizontal];
    return self;
}
- (BOOL)isFlipped{return YES;}
- (void)setFrameSize:(NSSize)size {[super setFrameSize:size];VFHeaderLayoutChanged(_owner);}
- (void)setBoundsSize:(NSSize)size {[super setBoundsSize:size];VFHeaderLayoutChanged(_owner);}
- (void)viewDidMoveToWindow {[super viewDidMoveToWindow];VFHeaderLayoutChanged(_owner);}
- (void)viewDidMoveToSuperview {[super viewDidMoveToSuperview];VFHeaderLayoutChanged(_owner);}
- (void)dealloc{_owner=nil;[_preferredWidth release];[_heightConstraint release];[super dealloc];}
- (NSSize)intrinsicContentSize{return NSMakeSize(NSViewNoIntrinsicMetric,_itemHeight);}
- (void)resizeSubviewsWithOldSize:(NSSize)oldSize {
    (void)oldSize; // Qt child frame and inverse-container geometry have exact owners.
    VFHeaderLayoutChanged(_owner);
}
- (void)didAddSubview:(NSView *)view{[super didAddSubview:view];VFHeaderLayoutChanged(_owner);}
- (void)willRemoveSubview:(NSView *)view{VFHeaderHostWillRemoveSubview(_owner,view);[super willRemoveSubview:view];}
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
@end

@interface VFHeaderHost : NSObject<NSToolbarDelegate> {
@public
    NSWindow *_window;
    NSToolbar *_toolbar,*_originalToolbar;
    NSToolbarItem *_item;
    VFHeaderContainer *_view;
    VFHeaderChildBinding *_childBinding;
    id _windowDelegate;
    NSAppearance *_originalAppearance,*_ownedAppearance;
    NSWindowToolbarStyle _originalStyle;
    BOOL _closed,_closing,_styleWritten,_toolbarAssigned,_appearanceWritten,_nativeClosed;
    BOOL _layingOut,_layoutValid,_eventPending,_pipeFailed,_haveEventSnapshot;
    double _eventSnapshot[98];unsigned _eventFlags;int _eventStatus;
    int _eventRead,_eventWrite;
    double _gutter,_minWidth;
    NSButton *_observedButtons[3];
    BOOL _buttonFrameFlags[3],_buttonBoundsFlags[3],_buttonKVOHidden[3],_buttonKVOWindow[3];
    NSWindow *_buttonWindows[3];
    CGFloat _height;
}
- (instancetype)initWithWindow:(NSWindow *)window height:(CGFloat)height gutter:(double)gutter minWidth:(double)minWidth;
- (void)layoutChanged;
- (void)changed:(NSNotification *)notification;
- (void)signal;
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
- (BOOL)stopObserving:(BOOL)restore {
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
        _originalToolbar=[window.toolbar retain];_originalStyle=window.toolbarStyle;
        _windowDelegate=[window.delegate retain];
        _originalAppearance=[window.appearance retain];
        _ownedAppearance=[[NSAppearance appearanceNamed:NSAppearanceNameDarkAqua] retain];
        if(!_ownedAppearance){[self release];return nil;}
        @try{window.appearance=_ownedAppearance;}
        @finally{_appearanceWritten=window.appearance==_ownedAppearance;}
        _view=[[VFHeaderContainer alloc] initWithHeight:height];_view->_owner=self;
        [self layoutChanged];
        if(!_layoutValid){[self release];return nil;}
        _item=[[NSToolbarItem alloc] initWithItemIdentifier:VFHeaderItemID];
        _item.view=_view;_item.label=@"VODForge";_item.bordered=NO;
        _item.visibilityPriority=NSToolbarItemVisibilityPriorityHigh;
        _toolbar=(NSToolbar *)[[VF_HEADER_TOOLBAR_CLASS alloc] initWithIdentifier:@"org.vodforge.qa.real-header-toolbar"];
        _toolbar.allowsUserCustomization=NO;_toolbar.autosavesConfiguration=NO;
        _toolbar.allowsExtensionItems=NO;_toolbar.displayMode=NSToolbarDisplayModeIconOnly;
        _toolbar.delegate=self;
        @try { window.toolbarStyle=NSWindowToolbarStyleUnified; }
        @finally { _styleWritten=window.toolbarStyle==NSWindowToolbarStyleUnified; }
        @try { window.toolbar=_toolbar; }
        @finally { _toolbarAssigned=window.toolbar==_toolbar; }
        _toolbar.visible=YES;
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
- (NSArray *)toolbarAllowedItemIdentifiers:(NSToolbar *)toolbar {
    return toolbar==_toolbar?@[VFHeaderItemID]:@[];
}
- (NSArray *)toolbarDefaultItemIdentifiers:(NSToolbar *)toolbar {
    return toolbar==_toolbar?@[VFHeaderItemID]:@[];
}
- (NSToolbarItem *)toolbar:(NSToolbar *)toolbar itemForItemIdentifier:(NSToolbarItemIdentifier)identifier willBeInsertedIntoToolbar:(BOOL)inserted {
    (void)inserted;
    return !_closed&&toolbar==_toolbar&&[identifier isEqualToString:VFHeaderItemID]?_item:nil;
}
- (BOOL)ownedGeneration {
    return _toolbarAssigned&&_styleWritten&&_window&&_toolbar&&_item&&_view
        &&_window.toolbar==_toolbar&&_toolbar.delegate==self&&_item.view==_view
        &&_window.delegate==_windowDelegate&&_window.toolbarStyle==NSWindowToolbarStyleUnified
        &&_appearanceWritten&&_window.appearance==_ownedAppearance;
}
- (BOOL)current { return !_closed&&!_nativeClosed&&!_pipeFailed&&_layoutValid&&[self ownedGeneration]; }
- (void)signal {
    if(_closed||![NSThread isMainThread]||_eventWrite<0||_eventPending)return;
    // Window updates can be frequent. Wake Qt only for actual bounded state
    // changes, never a read->same setter->native update feedback loop.
    double snapshot[98];BOOL changed=!_haveEventSnapshot;
    unsigned flags=vf_header_host_flags(self);int status=vf_header_host_state(self);
    if(flags!=_eventFlags||status!=_eventStatus)changed=YES;
    for(unsigned i=0;i<98;i++) {
        snapshot[i]=vf_header_host_geometry(self,i);
        if(!((isnan(snapshot[i])&&isnan(_eventSnapshot[i]))||snapshot[i]==_eventSnapshot[i]))changed=YES;
    }
    if(!changed)return;
    for(unsigned i=0;i<98;i++)_eventSnapshot[i]=snapshot[i];
    _eventFlags=flags;_eventStatus=status;_haveEventSnapshot=YES;
    unsigned char byte=1;ssize_t result;
    do{result=write(_eventWrite,&byte,1);}while(result<0&&errno==EINTR);
    if(result==1||(result<0&&(errno==EAGAIN||errno==EWOULDBLOCK)))_eventPending=YES;
    else if(result<0&&errno!=EINTR)_pipeFailed=YES;
}
- (void)stopButtons {
    NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
    for(unsigned i=0;i<3;i++)if(_observedButtons[i]) {
        NSButton *button=_observedButtons[i];
        if(_buttonKVOHidden[i]){@try{[button removeObserver:self forKeyPath:@"hidden" context:&VFHeaderKVOContext];}@catch(NSException *e){(void)e;}_buttonKVOHidden[i]=NO;}
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
    [self refreshButtons];[self layoutChanged];[self signal];
}
- (void)layoutChanged {
    if(_closed||_nativeClosed||_layingOut||![NSThread isMainThread]||!_view)return;
    _layingOut=YES;_layoutValid=NO;
    @try {
        NSView *content=_window.contentView;NSRect contentRect=[content convertRect:content.bounds toView:nil];
        double origin=NSMinX(contentRect)+_gutter;
        NSRect contentScreen=[_window convertRectToScreen:contentRect];
        if(_view.window) {
            NSRect hostScreen=[_view.window convertRectToScreen:[_view convertRect:_view.bounds toView:nil]];
            origin=NSMinX(contentRect)+NSMinX(hostScreen)-NSMinX(contentScreen);
        } else for(unsigned i=0;i<3;i++) {
            NSButton *b=[_window standardWindowButton:(NSWindowButton)i];
            if(b&&b.window) {
                NSRect screen=[b.window convertRectToScreen:[b convertRect:b.bounds toView:nil]];
                origin=fmax(origin,NSMinX(contentRect)+NSMaxX(screen)-NSMinX(contentScreen)+_gutter);
            }
        }
        double width=NSMaxX(contentRect)-origin-_gutter;
        if(isfinite(width)&&isfinite(origin)&&width>=_minWidth&&width>0) {
            if(fabs(_view->_preferredWidth.constant-width)>.01)_view->_preferredWidth.constant=width;
            // Initial allocation is meaningful before AppKit embeds the view.
            // Once attached AppKit owns its actual frame; constrain preferred
            // item width only, and report actual frame/screen geometry separately.
            if(!_view.window&&!NSEqualSizes(_view.frame.size,NSMakeSize(width,_height)))
                [_view setFrameSize:NSMakeSize(width,_height)];
            _layoutValid=YES;
        }
    } @catch(NSException *exception){(void)exception;}
    _layingOut=NO;[self signal];
}
- (void)willClose:(NSNotification *)notification {
    if(![NSThread isMainThread]||notification.object!=_window||_closed)return;
    _closing=YES;_nativeClosed=YES;[self signal];
}
- (void)close {
    if(_closed)return;_closed=YES;
    if(_childBinding){[_childBinding releaseOnly];[_childBinding release];_childBinding=nil;}
    if(_view)_view->_owner=nil;[self stopButtons];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    // Setter history distinguishes failed construction from a user later
    // returning the original toolbar. Identity alone does not prove ownership.
    @try {
        if(!_closing&&[self ownedGeneration]) {
            _window.toolbar=_originalToolbar;
            // The setter may invoke native callbacks. Recheck the whole still-
            // owned state before the second write; never overwrite a new style.
            if(_window.toolbar==_originalToolbar&&_toolbar.delegate==self
                &&_item.view==_view&&_window.delegate==_windowDelegate
                &&_window.toolbarStyle==NSWindowToolbarStyleUnified&&_window.appearance==_ownedAppearance) {
                _window.toolbarStyle=_originalStyle;
                if(_window.toolbar==_originalToolbar&&_window.toolbarStyle==_originalStyle
                    &&_window.delegate==_windowDelegate&&_window.appearance==_ownedAppearance)
                    _window.appearance=_originalAppearance;
            }
        } else if(!_closing&&!_toolbarAssigned&&_styleWritten&&_toolbar&&_item&&_view
            &&_window.toolbar==_originalToolbar&&_toolbar.delegate==self&&_item.view==_view
            &&_window.delegate==_windowDelegate&&_window.toolbarStyle==NSWindowToolbarStyleUnified
            &&_window.appearance==_ownedAppearance) {
            // This constructor never assigned its toolbar. Only its identifiable
            // attempted style on the unchanged original generation is restored.
            _window.toolbarStyle=_originalStyle;
        }
        // Appearance can precede view/style/toolbar construction. A partial
        // constructor restores it only on the unchanged original generation.
        if(!_closing&&!_toolbarAssigned&&_appearanceWritten
            &&_window.toolbar==_originalToolbar&&_window.toolbarStyle==_originalStyle
            &&_window.delegate==_windowDelegate&&_window.appearance==_ownedAppearance)
            _window.appearance=_originalAppearance;
    } @catch(NSException *exception) {(void)exception;}
    // Remove only our delegate reference before releasing its receiver. Do not
    // replace a foreign delegate even when the toolbar itself is still attached.
    if(_toolbar.delegate==self)_toolbar.delegate=nil;
    [_item release];_item=nil;[_view release];_view=nil;
    [_toolbar release];_toolbar=nil;[_originalToolbar release];_originalToolbar=nil;
    [_windowDelegate release];_windowDelegate=nil;
    [_originalAppearance release];_originalAppearance=nil;[_ownedAppearance release];_ownedAppearance=nil;
    [_window release];_window=nil;
    if(_eventRead>=0){close(_eventRead);_eventRead=-1;}
    if(_eventWrite>=0){close(_eventWrite);_eventWrite=-1;}
}
- (void)dealloc{[self close];[super dealloc];}
@end
unsigned vf_header_host_abi_version(void){return 2;}
void *vf_header_host_create(void *window,double height,double gutter,double minWidth) {
    if(![NSThread isMainThread]||!window||!isfinite(height)||height<=0||height>256
        ||!isfinite(gutter)||gutter<0||gutter>256||!isfinite(minWidth)||minWidth<=0||minWidth>16384)return NULL;
    @try {
        if(![(id)window isKindOfClass:[NSWindow class]])return NULL;
        // An existing exact native owner may still be retiring a Qt child.
        // Never nest hosts or steal its toolbar before that owner releases it.
        if([[[(NSWindow *)window toolbar] delegate] isKindOfClass:[VFHeaderHost class]])return NULL;
        // Body remains full-size. Prototype does not enable flags after creation.
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
        if(index==22)return h->_toolbar.visible;
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
        if([h current])flags|=1;if(h->_view.window)flags|=2;if(h->_toolbar.visible)flags|=4;
        if(h->_window.delegate==h->_windowDelegate)flags|=8;
        if(h->_window.styleMask&NSWindowStyleMaskFullScreen)flags|=16;
        NSButton *b=[h->_window standardWindowButton:NSWindowCloseButton];
        if(b&&b.window) {
            BOOL hidden=b.hiddenOrHasHiddenAncestor||NSIsEmptyRect(b.visibleRect);
            if(hidden)flags|=128;
            else if(b.window.visible)flags|=32;
        }
        if(h->_layoutValid)flags|=64;
        if(h->_childBinding){flags|=256;if([h->_childBinding current])flags|=512;if([h->_childBinding fit])flags|=1024;}
    } @catch(NSException *exception){(void)exception;}
    return flags;
}

int vf_header_host_set_height(void *handle,double height) {
    if(vf_header_host_state(handle)!=1||!isfinite(height)||height<=0||height>256)return 0;
    VFHeaderHost *h=handle;double before=h->_height;
    if(fabs(height-before)<.01)return 1;
    @try {
        h->_view->_heightConstraint.constant=height;
        h->_view->_itemHeight=height;h->_height=height;
        [h->_view invalidateIntrinsicContentSize];[h layoutChanged];
        return h->_layoutValid?1:0;
    } @catch(NSException *exception) {
        (void)exception;
        @try {h->_view->_heightConstraint.constant=before;h->_view->_itemHeight=before;h->_height=before;[h layoutChanged];}
        @catch(NSException *rollbackException){(void)rollbackException;}
        return 0;
    }
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
