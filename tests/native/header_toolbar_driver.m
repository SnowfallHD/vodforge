#import <AppKit/AppKit.h>
#include <stdio.h>
#include <stdlib.h>
#define REQUIRE(c) do{if(!(c)){fprintf(stderr,"refused:%s:%d\n",#c,__LINE__);exit(3);}}while(0)
@interface VFToolbar:NSObject
@property(assign) id delegate;
@property BOOL allowsUserCustomization,autosavesConfiguration,allowsExtensionItems,visible,allowsDisplayModeCustomization;
@property NSToolbarDisplayMode displayMode;
@end
@implementation VFToolbar
@end
#define VF_TOOLBAR_CLASS VFToolbar
#import "../../yt_downloader/platforms/macos/header_toolbar.m"
@interface VFWindow:NSObject
@property(retain) id delegate;
@property(retain) NSView *contentView;
@property(nonatomic,retain) NSToolbar *toolbar;
@property NSWindowToolbarStyle toolbarStyle;
@property NSWindowStyleMask styleMask;
@property BOOL titlebarAppearsTransparent,throwBefore,throwAfter;
@property NSWindowTitleVisibility titleVisibility;
@property(retain) NSArray *titlebarAccessoryViewControllers;
@end
@implementation VFWindow
- (BOOL)isKindOfClass:(Class)c{return c==NSWindow.class||[super isKindOfClass:c];}
- (NSButton *)standardWindowButton:(NSWindowButton)i{(void)i;return nil;}
- (instancetype)init{self=[super init];self.contentView=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,1100,740)]autorelease];self.delegate=[[[NSObject alloc]init]autorelease];self.styleMask=NSWindowStyleMaskFullSizeContentView;self.titlebarAppearsTransparent=YES;self.titleVisibility=NSWindowTitleHidden;self.titlebarAccessoryViewControllers=@[];self.toolbarStyle=NSWindowToolbarStyleAutomatic;return self;}
- (void)setToolbar:(NSToolbar *)value{if(value&&self.throwBefore)[NSException raise:@"before" format:@"fixture"];[value retain];[_toolbar release];_toolbar=value;if(value&&self.throwAfter)[NSException raise:@"after" format:@"fixture"];}
- (void)dealloc{[_contentView release];[_delegate release];[_toolbar release];[_titlebarAccessoryViewControllers release];[super dealloc];}
@end
int main(int argc,char **argv){@autoreleasepool{
 REQUIRE(argc==2&&NSApp==nil);VFWindow *w=[VFWindow new];NSString *test=@(argv[1]);id delegate=w.delegate;
 if([test isEqual:@"setter_before_failure"]||[test isEqual:@"setter_failure"]){
   w.throwBefore=[test isEqual:@"setter_before_failure"];w.throwAfter=!w.throwBefore;
   void *failed=vf_header_host_create(w,44,20,64);REQUIRE(!failed&&!w.toolbar&&w.toolbarStyle==NSWindowToolbarStyleAutomatic);[w release];
 }else{
 void *h=vf_header_host_create(w,44,20,64);REQUIRE(h&&vf_header_host_state(h)==1&&vf_header_host_abi_version()==4);VFHeaderHost *o=h;
 REQUIRE(o->_view.isFlipped&&o->_carrier->_view==o->_view&&o->_view.fittingSize.height==44);
 REQUIRE(vf_header_host_set_height(h,44)&&!vf_header_host_set_height(h,32));
 if([test isEqual:@"guards"]){REQUIRE(!vf_header_host_create(NULL,44,20,64));REQUIRE(!vf_header_host_create(w,32,20,64));REQUIRE(!vf_header_host_create(w,NAN,20,64));REQUIRE(!vf_header_host_create(w,44,-1,64));REQUIRE(!vf_header_host_create(w,44,20,0));}
 if([test isEqual:@"duplicate_host"]){REQUIRE(!vf_header_host_create(w,44,20,64));REQUIRE(w.toolbar==o->_carrier->_toolbar);}
 if([test isEqual:@"events"]){REQUIRE(vf_header_host_drain(h)>=0);[o changed:[NSNotification notificationWithName:NSWindowWillEnterFullScreenNotification object:w]];REQUIRE(o->_transition==1&&vf_header_host_drain(h)>0);[o changed:[NSNotification notificationWithName:NSWindowDidEnterFullScreenNotification object:w]];REQUIRE(o->_transition==0&&vf_header_host_drain(h)>0);[o signal];REQUIRE(vf_header_host_drain(h)==0);}
 if([test isEqual:@"foreign_notification"]){REQUIRE(vf_header_host_drain(h)>=0);[o changed:[NSNotification notificationWithName:NSWindowWillEnterFullScreenNotification object:[NSObject new]]];REQUIRE(o->_transition==0&&vf_header_host_drain(h)==0);}
 if([test isEqual:@"foreign"]){id own=[w.toolbar retain];w.toolbar=(id)[[[NSObject alloc]init]autorelease];REQUIRE(!vf_header_host_destroy(&h)&&h);w.toolbar=own;[own release];}
 if([test isEqual:@"window_delegate"]){id old=[w.delegate retain];w.delegate=[[[NSObject alloc]init]autorelease];REQUIRE(!vf_header_host_destroy(&h)&&h);w.delegate=old;[old release];}
 if([test isEqual:@"changed_toolbar_delegate"]){id old=[w.toolbar.delegate retain];w.toolbar.delegate=nil;REQUIRE(!vf_header_host_destroy(&h)&&h);w.toolbar.delegate=old;[old release];}
 if([test isEqual:@"changed_item_view"]){NSView *old=[o->_carrier->_item.view retain];o->_carrier->_item.view=[[[NSView alloc]init]autorelease];REQUIRE(!vf_header_host_destroy(&h)&&h);o->_carrier->_item.view=old;[old release];}
 if([test isEqual:@"changed_style"]){w.toolbarStyle=NSWindowToolbarStyleExpanded;REQUIRE(!vf_header_host_destroy(&h)&&h);w.toolbarStyle=NSWindowToolbarStyleUnified;}
 if([test isEqual:@"foreign_accessory"]){w.titlebarAccessoryViewControllers=@[[[[NSObject alloc]init]autorelease]];REQUIRE(!vf_header_host_destroy(&h)&&h);w.titlebarAccessoryViewControllers=@[];}
 if([test isEqual:@"bound_subview"]){NSView *child=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,1,1)]autorelease];[o->_view addSubview:child];REQUIRE(!vf_header_host_destroy(&h)&&h);[child removeFromSuperview];}
 int fd=vf_header_host_event_fd(h);REQUIRE(fd>=0);
 REQUIRE(vf_header_host_destroy(&h)&&!h&&!w.toolbar&&w.toolbarStyle==NSWindowToolbarStyleAutomatic&&w.delegate==delegate);
 REQUIRE(fcntl(fd,F_GETFD)==-1&&errno==EBADF);REQUIRE(vf_header_host_destroy(&h));
 [w release];}
 REQUIRE(NSApp==nil);printf("{\"case\":\"%s\",\"passed\":true,\"nsapp_created\":false}\n",argv[1]);
}return 0;}
