#import <AppKit/AppKit.h>
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(condition) do {if(!(condition)){fprintf(stderr,"check_failed:%s:%d\n",#condition,__LINE__);exit(3);}}while(0)
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
@interface VFTestToolbar : NSObject
@property(assign) id<NSToolbarDelegate> delegate;
@property BOOL allowsUserCustomization,autosavesConfiguration,allowsExtensionItems;
@property(getter=isVisible) BOOL visible;
@property NSToolbarDisplayMode displayMode;
- (id)initWithIdentifier:(NSString *)identifier;
@end
@implementation VFTestToolbar
- (id)initWithIdentifier:(NSString *)identifier{(void)identifier;return [super init];}
@end
#define VF_HEADER_TOOLBAR_CLASS VFTestToolbar
#ifndef VF_HEADER_HOST_SOURCE
#define VF_HEADER_HOST_SOURCE "../../yt_downloader/platforms/macos/header_toolbar.m"
#endif
#import VF_HEADER_HOST_SOURCE

static unsigned toolbarWrites,styleWrites,delegateWrites,buttonReads,appearanceWrites;
@interface VFTestHeaderButton : NSObject {
    NSRect _frame;
}
@property(nonatomic) NSRect frame;
@property NSRect bounds;
@property(assign) NSWindow *window;
@property(getter=isHidden) BOOL hidden;
@property BOOL postsFrameChangedNotifications,postsBoundsChangedNotifications;
- (BOOL)isHiddenOrHasHiddenAncestor;
- (NSRect)visibleRect;
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view;
@end
@implementation VFTestHeaderButton
@synthesize frame=_frame;
- (void)setFrame:(NSRect)rect{_frame=rect;if(self.postsFrameChangedNotifications)
    [[NSNotificationCenter defaultCenter]postNotificationName:NSViewFrameDidChangeNotification object:self];}
- (BOOL)isHiddenOrHasHiddenAncestor{return self.hidden;}
- (NSRect)visibleRect{return self.hidden?NSZeroRect:self.bounds;}
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view{(void)view;rect.origin.x+=self.frame.origin.x;rect.origin.y+=self.frame.origin.y;return rect;}
@end
@interface VFTestWindow : NSObject {
    NSToolbar *_toolbar;
    NSWindowToolbarStyle _toolbarStyle;
    id _delegate;
    NSAppearance *_appearance;
@public
    VFTestHeaderButton *_buttons[3];
}
@property(nonatomic,retain) id delegate;
@property(nonatomic,retain) NSAppearance *appearance;
@property NSWindowStyleMask styleMask;
@property(retain) NSView *contentView;
@property NSRect frame,contentLayoutRect;
@property(nonatomic,retain) NSToolbar *toolbar;
@property(nonatomic) NSWindowToolbarStyle toolbarStyle;
@property BOOL throwToolbar,throwBeforeToolbar;
@property(getter=isVisible) BOOL visible;
@end
@implementation VFTestWindow
@synthesize toolbar=_toolbar,toolbarStyle=_toolbarStyle,delegate=_delegate,appearance=_appearance;
- (void)setAppearance:(NSAppearance *)value{appearanceWrites++;[value retain];[_appearance release];_appearance=value;}
- (void)setDelegate:(id)value{delegateWrites++;[value retain];[_delegate release];_delegate=value;}
- (instancetype)init {
    self=[super init];if(!self)return nil;
    self.contentView=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,1100,740)]autorelease];
    self.contentLayoutRect=self.contentView.frame;self.frame=self.contentView.frame;
    self.styleMask=NSWindowStyleMaskFullSizeContentView;return self;
}
- (BOOL)isKindOfClass:(Class)class{return class==[NSWindow class]||[super isKindOfClass:class];}
- (void)setToolbar:(NSToolbar *)toolbar {
    toolbarWrites++;if(self.throwBeforeToolbar){self.throwBeforeToolbar=NO;[NSException raise:@"controlledBeforeSetter" format:@"controlled"];}
    [toolbar retain];[_toolbar release];_toolbar=toolbar;
    if(self.throwToolbar){self.throwToolbar=NO;[NSException raise:@"controlledSetter" format:@"controlled"];}
}
- (void)setToolbarStyle:(NSWindowToolbarStyle)style{styleWrites++;_toolbarStyle=style;}
- (NSButton *)standardWindowButton:(NSWindowButton)button{buttonReads++;return button<3?(NSButton *)_buttons[button]:nil;}
- (NSRect)convertRectToScreen:(NSRect)rect{rect.origin.x+=self.frame.origin.x;rect.origin.y+=self.frame.origin.y;return rect;}
- (void)dealloc{for(unsigned i=0;i<3;i++)[_buttons[i] release];[_delegate release];[_appearance release];[_contentView release];[_toolbar release];[super dealloc];}
@end
static VFTestWindow *makeWindow(void) {
    VFTestWindow *w=[VFTestWindow new];w.delegate=[[[NSObject alloc]init]autorelease];
    w.toolbar=(id)[[[VFTestToolbar alloc]initWithIdentifier:@"original"]autorelease];
    w.toolbarStyle=NSWindowToolbarStyleExpanded;w.appearance=[NSAppearance appearanceNamed:NSAppearanceNameAqua];delegateWrites=0;return w;
}
static void basic(void) {
    VFTestWindow *w=makeWindow();id delegate=w.delegate,old=[w.toolbar retain];
    unsigned before=toolbarWrites;void *h=vf_header_host_create(w,50,12,300);assert(h&&vf_header_host_abi_version()==1);
    assert(vf_header_host_state(h)==1&&vf_header_host_view(h));assert(w.delegate==delegate);
    assert(w.toolbarStyle==NSWindowToolbarStyleUnified&&toolbarWrites==before+1);
    VFHeaderHost *host=h;assert(host->_toolbar.delegate==(id)host&&!host->_toolbar.autosavesConfiguration);
    assert([[host toolbarDefaultItemIdentifiers:host->_toolbar]count]==1);
    assert([host toolbar:host->_toolbar itemForItemIdentifier:VFHeaderItemID willBeInsertedIntoToolbar:YES].view==host->_view);
    assert(![host toolbar:host->_toolbar itemForItemIdentifier:@"foreign" willBeInsertedIntoToolbar:YES]);
    assert([host toolbarDefaultItemIdentifiers:(id)old].count==0);
    assert(vf_header_host_geometry(h,20)==50&&vf_header_host_geometry(h,23)==1);
    assert(isnan(vf_header_host_geometry(h,24))&&isnan(vf_header_host_geometry(h,66)));
    assert(vf_header_host_destroy(&h)&&!h&&vf_header_host_destroy(&h));
    assert(w.toolbar==old&&w.toolbarStyle==NSWindowToolbarStyleExpanded&&w.delegate==delegate);
    assert(buttonReads>0);[old release];[w release];
}
static void foreign(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    id replacement=[[[VFTestToolbar alloc]initWithIdentifier:@"replacement"]autorelease];
    w.toolbar=replacement;w.toolbarStyle=NSWindowToolbarStyleUnifiedCompact;
    unsigned before=toolbarWrites,styleBefore=styleWrites;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h)&&isnan(vf_header_host_geometry(h,0)));
    vf_header_host_destroy(&h);assert(w.toolbar==replacement&&toolbarWrites==before&&styleWrites==styleBefore);[w release];
}
static void windowDelegate(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    id replacement=[[[NSObject alloc]init]autorelease];w.delegate=replacement;delegateWrites=0;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h));vf_header_host_destroy(&h);
    assert(w.delegate==replacement);[w release];
}
static void nativeClose(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    unsigned before=toolbarWrites,styleBefore=styleWrites,appearanceBefore=appearanceWrites;
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowWillCloseNotification object:w];
    assert(vf_header_host_state(h)==-1&&!vf_header_host_view(h));
    vf_header_host_destroy(&h);assert(toolbarWrites==before&&styleWrites==styleBefore&&appearanceWrites==appearanceBefore);[w release];
}
static void guards(void) {
    VFTestWindow *w=makeWindow();unsigned before=toolbarWrites;
    assert(!vf_header_host_create(w,NAN,12,300)&&!vf_header_host_create(w,0,12,300)&&!vf_header_host_create(w,257,12,300));
    w.styleMask=0;assert(!vf_header_host_create(w,50,12,300));assert(toolbarWrites==before);[w release];
}
static void setterFailure(void) {
    VFTestWindow *w=makeWindow();id old=[w.toolbar retain];w.throwToolbar=YES;
    assert(!vf_header_host_create(w,50,12,300));assert(w.toolbar==old&&w.toolbarStyle==NSWindowToolbarStyleExpanded);
    assert([w.appearance.name isEqualToString:NSAppearanceNameAqua]);
    [old release];[w release];
}
static void setterBeforeFailure(void) {
    VFTestWindow *w=makeWindow();id old=[w.toolbar retain];w.throwBeforeToolbar=YES;
    assert(!vf_header_host_create(w,50,12,300));assert(w.toolbar==old&&w.toolbarStyle==NSWindowToolbarStyleExpanded);
    assert([w.appearance.name isEqualToString:NSAppearanceNameAqua]);
    [old release];[w release];
}
typedef struct{VFTestWindow *w;void *h;} ThreadInput;
static void *otherThread(void *value) {
    ThreadInput *i=value;void *h=i->h;
    assert(!vf_header_host_create(i->w,50,12,300)&&vf_header_host_state(h)==-1&&!vf_header_host_view(h));
    assert(isnan(vf_header_host_geometry(h,0))&&!vf_header_host_destroy(&h)&&h==i->h);
    assert(vf_header_host_event_fd(h)==-1&&vf_header_host_drain(h)==-1&&vf_header_host_flags(h)==0);
    assert(!vf_header_host_set_height(h,100));return NULL;
}
static void threadGuard(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    unsigned before=toolbarWrites,styleBefore=styleWrites;ThreadInput i={w,h};pthread_t t;
    assert(!pthread_create(&t,NULL,otherThread,&i)&&!pthread_join(t,NULL));
    assert(toolbarWrites==before&&styleWrites==styleBefore&&vf_header_host_state(h)==1);
    vf_header_host_destroy(&h);[w release];
}
static void autoresize(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    NSView *host=vf_header_host_view(h),*child=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,1,1)]autorelease];
    [host addSubview:child];host.frame=NSMakeRect(0,0,870,50);
    assert(NSEqualRects(child.frame,host.bounds)&&host.isFlipped);
    assert(w.contentView.bounds.size.height==740&&w.contentLayoutRect.size.height==740);
    void *saved=h;int fd=vf_header_host_event_fd(h);
    assert(!vf_header_host_destroy(&h)&&h==saved&&vf_header_host_state(h)==1&&fcntl(fd,F_GETFD)>=0);
    [child removeFromSuperview];
    assert(vf_header_host_destroy(&h)&&!h&&fcntl(fd,F_GETFD)==-1);[w release];
}
static void metadata(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    assert(isnan(vf_header_host_geometry(h,27))); // Not attached to an actual window.
    for(unsigned i=0;i<3;i++) {
        assert(vf_header_host_geometry(h,31+10*i)==0);
        assert(isnan(vf_header_host_geometry(h,32+10*i)));
    }
    assert(isnan(vf_header_host_geometry(h,61))&&NSApp==nil);
    vf_header_host_destroy(&h);[w release];
}
static void changedToolbarDelegate(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    VFHeaderHost *host=h;id toolbar=[w.toolbar retain],delegate=[[[NSObject alloc]init]autorelease];
    host->_toolbar.delegate=delegate;
    unsigned tw=toolbarWrites,sw=styleWrites;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h));
    vf_header_host_destroy(&h);
    assert(w.toolbar==toolbar&&toolbarWrites==tw&&styleWrites==sw&&[(NSToolbar *)toolbar delegate]==delegate);
    [toolbar release];[w release];
}
static void changedItemView(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    VFHeaderHost *host=h;NSToolbarItem *item=[host->_item retain];id toolbar=[w.toolbar retain];
    NSView *replacement=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,300,40)]autorelease];item.view=replacement;
    unsigned tw=toolbarWrites,sw=styleWrites;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h));
    vf_header_host_destroy(&h);
    assert(w.toolbar==toolbar&&toolbarWrites==tw&&styleWrites==sw&&item.view==replacement);
    [toolbar release];[item release];[w release];
}
static void changedStyle(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);id toolbar=[w.toolbar retain];
    w.toolbarStyle=NSWindowToolbarStyleUnifiedCompact;unsigned tw=toolbarWrites,sw=styleWrites;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h));
    vf_header_host_destroy(&h);
    assert(w.toolbar==toolbar&&w.toolbarStyle==NSWindowToolbarStyleUnifiedCompact&&toolbarWrites==tw&&styleWrites==sw);
    [toolbar release];[w release];
}
static void returnedOriginalToolbar(void) {
    VFTestWindow *w=makeWindow();id old=[w.toolbar retain];void *h=vf_header_host_create(w,50,12,300);assert(h);
    w.toolbar=old;unsigned tw=toolbarWrites,sw=styleWrites;
    assert(vf_header_host_state(h)==0);vf_header_host_destroy(&h);
    assert(w.toolbar==old&&w.toolbarStyle==NSWindowToolbarStyleUnified&&toolbarWrites==tw&&styleWrites==sw);
    [old release];[w release];
}

static void eventPipe(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    int fd=vf_header_host_event_fd(h);assert(fd>=0);
    assert((fcntl(fd,F_GETFL)&O_NONBLOCK)&&(fcntl(fd,F_GETFD)&FD_CLOEXEC));
    assert(vf_header_host_drain(h)==1&&vf_header_host_drain(h)==0);
    NSView *view=vf_header_host_view(h);view.frame=NSMakeRect(0,0,900,50);
    assert(vf_header_host_drain(h)==1);
    VFHeaderHost *host=h;
    // Drain the first post-constructor snapshot if native update observed one.
    [host signal];vf_header_host_drain(h);
    for(unsigned i=0;i<100;i++)[host signal];
    assert(vf_header_host_drain(h)==0);
    w.frame=NSMakeRect(1,0,1100,740);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidMoveNotification object:w];
    assert(vf_header_host_drain(h)==1);
    for(unsigned i=2;i<=100;i++) {
        w.frame=NSMakeRect(i,0,1100,740);
        [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidMoveNotification object:w];
    }
    assert(vf_header_host_drain(h)==1&&vf_header_host_geometry(h,16)==100);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowWillCloseNotification object:w];
    assert(vf_header_host_drain(h)==1&&vf_header_host_event_fd(h)==fd);
    assert(vf_header_host_state(h)==-1&&vf_header_host_flags(h)==0);
    vf_header_host_destroy(&h);assert(fcntl(fd,F_GETFD)==-1&&errno==EBADF);[w release];
}
static void foreignNotification(void) {
    VFTestWindow *w=makeWindow(),*other=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    assert(vf_header_host_drain(h)==1);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidResizeNotification object:other];
    assert(vf_header_host_drain(h)==0&&vf_header_host_state(h)==1);
    vf_header_host_destroy(&h);[other release];[w release];
}
static void autoSize(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);
    NSView *view=vf_header_host_view(h);assert(view.bounds.size.width==1076);
    assert((vf_header_host_flags(h)&(1|4|8|64))==(1|4|8|64));
    w.contentView.frame=NSMakeRect(0,0,800,740);w.contentView.bounds=NSMakeRect(0,0,800,740);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidResizeNotification object:w];
    assert(view.bounds.size.width==776&&vf_header_host_state(h)==1);
    w.contentView.frame=NSMakeRect(0,0,200,740);w.contentView.bounds=NSMakeRect(0,0,200,740);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidResizeNotification object:w];
    assert(vf_header_host_state(h)==0&&!(vf_header_host_flags(h)&64));
    w.contentView.frame=NSMakeRect(0,0,900,740);w.contentView.bounds=NSMakeRect(0,0,900,740);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidResizeNotification object:w];
    assert(vf_header_host_state(h)==1&&view.bounds.size.width==876);
    assert(w.contentView.bounds.size.height==740);vf_header_host_destroy(&h);[w release];
}

static void setHeight(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,44,12,300);assert(h);
    assert(vf_header_host_drain(h)==1);
    assert(!vf_header_host_set_height(h,NAN)&&!vf_header_host_set_height(h,0)&&!vf_header_host_set_height(h,257));
    assert(vf_header_host_drain(h)==0&&vf_header_host_geometry(h,20)==44);
    assert(vf_header_host_set_height(h,100)&&vf_header_host_geometry(h,20)==100);
    assert(((NSView *)vf_header_host_view(h)).bounds.size.height==100&&vf_header_host_drain(h)==1);
    w.toolbarStyle=NSWindowToolbarStyleUnifiedCompact;
    assert(!vf_header_host_set_height(h,44));vf_header_host_destroy(&h);[w release];
}

static void buttonEvents(void) {
    VFTestWindow *w=makeWindow();w.visible=YES;
    for(unsigned i=0;i<3;i++) {
        VFTestHeaderButton *button=[VFTestHeaderButton new];button.window=(NSWindow *)w;
        button.frame=NSMakeRect(7+20*i,718,14,16);button.bounds=NSMakeRect(0,0,14,16);
        if(i==1){button.postsFrameChangedNotifications=YES;button.postsBoundsChangedNotifications=YES;}
        w->_buttons[i]=button;
    }
    void *h=vf_header_host_create(w,50,12,300);assert(h);
    NSView *host=vf_header_host_view(h);assert(host.bounds.size.width==1015); // Actual max buttonX61+gutter12, rightgutter12.
    assert(vf_header_host_flags(h)&32);
    assert(vf_header_host_geometry(h,31)==1&&vf_header_host_geometry(h,32)==1);
    assert(vf_header_host_geometry(h,33)==7&&vf_header_host_geometry(h,35)==14);
    assert(vf_header_host_geometry(h,64)==1100&&vf_header_host_geometry(h,65)==740);
    assert(w->_buttons[0].postsFrameChangedNotifications&&w->_buttons[0].postsBoundsChangedNotifications);
    assert(vf_header_host_drain(h)==1);
    w->_buttons[0].hidden=YES;assert(vf_header_host_drain(h)==1&&!(vf_header_host_flags(h)&32)&&(vf_header_host_flags(h)&128));
    w->_buttons[0].hidden=NO;assert(vf_header_host_drain(h)==1);
    w->_buttons[0].frame=NSMakeRect(9,718,14,16);assert(vf_header_host_drain(h)==1);
    w.visible=NO;assert(!(vf_header_host_flags(h)&(32|128))); // Window occlusion alone is unknown.
    VFTestWindow *aux=makeWindow();aux.visible=YES;aux.frame=NSMakeRect(100,0,1100,740);
    for(unsigned i=0;i<3;i++)w->_buttons[i].window=(NSWindow *)aux;
    assert(vf_header_host_state(h)==1&&host.bounds.size.width==915);
    assert(vf_header_host_geometry(h,32)==0&&vf_header_host_geometry(h,37)==109);
    assert(vf_header_host_flags(h)&32);
    [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowDidUpdateNotification object:w];
    w->_buttons[0].hidden=YES;assert(vf_header_host_flags(h)&128);
    vf_header_host_destroy(&h);[aux release];
    for(unsigned i=0;i<3;i++)assert(w->_buttons[i].postsFrameChangedNotifications==(i==1)&&w->_buttons[i].postsBoundsChangedNotifications==(i==1));
    // Removed observers must not call the released owner.
    w->_buttons[0].hidden=YES;[w release];
}

static void duplicateHost(void) {
    VFTestWindow *w=makeWindow();void *first=vf_header_host_create(w,50,12,300);assert(first);
    id toolbar=w.toolbar;unsigned tw=toolbarWrites,sw=styleWrites,aw=appearanceWrites;
    void *second=vf_header_host_create(w,100,12,300);
    assert(!second&&w.toolbar==toolbar&&toolbarWrites==tw&&styleWrites==sw&&appearanceWrites==aw);
    assert(vf_header_host_state(first)==1);vf_header_host_destroy(&first);[w release];
}

static void darkAppearance(void) {
    VFTestWindow *w=makeWindow();id original=[w.appearance retain];void *h=vf_header_host_create(w,50,12,300);assert(h);
    assert([w.appearance.name isEqualToString:NSAppearanceNameDarkAqua]);
    vf_header_host_destroy(&h);assert(w.appearance==original);[original release];[w release];
    w=makeWindow();w.appearance=nil;h=vf_header_host_create(w,50,12,300);assert(h);
    vf_header_host_destroy(&h);assert(w.appearance==nil);[w release];
}
static void foreignAppearance(void) {
    VFTestWindow *w=makeWindow();void *h=vf_header_host_create(w,50,12,300);assert(h);id toolbar=w.toolbar;
    w.appearance=[NSAppearance appearanceNamed:NSAppearanceNameAqua];unsigned aw=appearanceWrites,tw=toolbarWrites,sw=styleWrites;
    assert(vf_header_host_state(h)==0&&!vf_header_host_view(h));vf_header_host_destroy(&h);
    assert(w.appearance.name==NSAppearanceNameAqua||[w.appearance.name isEqualToString:NSAppearanceNameAqua]);
    assert(appearanceWrites==aw&&toolbarWrites==tw&&styleWrites==sw&&w.toolbar==toolbar);[w release];
}

int main(int argc,const char **argv) {
 @autoreleasepool {
    assert(argc==2&&NSApp==nil);
    if(!strcmp(argv[1],"basic"))basic();else if(!strcmp(argv[1],"foreign"))foreign();
    else if(!strcmp(argv[1],"window_delegate"))windowDelegate();else if(!strcmp(argv[1],"native_close"))nativeClose();
    else if(!strcmp(argv[1],"guards"))guards();else if(!strcmp(argv[1],"setter_failure"))setterFailure();
    else if(!strcmp(argv[1],"setter_before_failure"))setterBeforeFailure();
    else if(!strcmp(argv[1],"thread"))threadGuard();else if(!strcmp(argv[1],"autoresize"))autoresize();
    else if(!strcmp(argv[1],"metadata"))metadata();
    else if(!strcmp(argv[1],"changed_toolbar_delegate"))changedToolbarDelegate();
    else if(!strcmp(argv[1],"changed_item_view"))changedItemView();
    else if(!strcmp(argv[1],"changed_style"))changedStyle();
    else if(!strcmp(argv[1],"returned_original_toolbar"))returnedOriginalToolbar();else if(!strcmp(argv[1],"event_pipe"))eventPipe();
    else if(!strcmp(argv[1],"foreign_notification"))foreignNotification();
    else if(!strcmp(argv[1],"auto_size"))autoSize();else if(!strcmp(argv[1],"set_height"))setHeight();else if(!strcmp(argv[1],"button_events"))buttonEvents();else if(!strcmp(argv[1],"duplicate_host"))duplicateHost();else if(!strcmp(argv[1],"dark_appearance"))darkAppearance();
    else if(!strcmp(argv[1],"foreign_appearance"))foreignAppearance();else return 2;
    assert(NSApp==nil&&delegateWrites==0);
    printf("{\"case\":\"%s\",\"passed\":true,\"nsapp_created\":false}\n",argv[1]);
 }return 0;
}
