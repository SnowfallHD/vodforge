#import <AppKit/AppKit.h>
#include <stdio.h>
#include <stdlib.h>
#import <objc/runtime.h>
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
@property(retain) NSColor *backgroundColor;
@property(nonatomic,retain) NSToolbar *toolbar;
@property NSWindowToolbarStyle toolbarStyle;
@property NSRect frame;
@property(readonly) NSRect contentLayoutRect;
@property NSWindowStyleMask styleMask;
@property BOOL titlebarAppearsTransparent,throwBefore,throwAfter;
@property NSWindowTitleVisibility titleVisibility;
@property(retain) NSArray *titlebarAccessoryViewControllers;
@end
@implementation VFWindow
- (NSRect)contentLayoutRect{return self.contentView.bounds;}
- (NSRect)convertRectToScreen:(NSRect)r{return r;}
- (BOOL)isKindOfClass:(Class)c{return c==NSWindow.class||[super isKindOfClass:c];}
- (NSButton *)standardWindowButton:(NSWindowButton)i{(void)i;return nil;}
- (instancetype)init{self=[super init];self.contentView=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,1100,740)]autorelease];self.delegate=[[[NSObject alloc]init]autorelease];self.styleMask=NSWindowStyleMaskFullSizeContentView;self.titlebarAppearsTransparent=YES;self.titleVisibility=NSWindowTitleHidden;self.titlebarAccessoryViewControllers=@[];self.toolbarStyle=NSWindowToolbarStyleAutomatic;return self;}
- (void)setToolbar:(NSToolbar *)value{if(value&&self.throwBefore)[NSException raise:@"before" format:@"fixture"];[value retain];[_toolbar release];_toolbar=value;if(value&&self.throwAfter)[NSException raise:@"after" format:@"fixture"];}
- (void)dealloc{[_backgroundColor release];[_contentView release];[_delegate release];[_toolbar release];[_titlebarAccessoryViewControllers release];[super dealloc];}
@end
static NSWindow *brandWindow;
@interface VFBrandView:VFHeaderContainer
@end
@implementation VFBrandView
- (NSWindow *)window{return brandWindow;}
@end
static BOOL callbackInFlight;
@interface VFCallbackHost:VFHeaderHost
@end
@implementation VFCallbackHost
- (void)dealloc{REQUIRE(!callbackInFlight);[super dealloc];}
@end
static void retireNow(void *context){callbackInFlight=YES;REQUIRE(vf_header_host_destroy((void **)context));callbackInFlight=NO;}
static void changedNow(void *context){(*(unsigned *)context)++;}
int main(int argc,char **argv){@autoreleasepool{
 REQUIRE(argc==2&&NSApp==nil);VFWindow *w=[VFWindow new];NSString *test=@(argv[1]);id delegate=w.delegate;
 if([test isEqual:@"setter_before_failure"]||[test isEqual:@"setter_failure"]){
   w.throwBefore=[test isEqual:@"setter_before_failure"];w.throwAfter=!w.throwBefore;
   void *failed=vf_header_host_create(w,44,20,64);REQUIRE(!failed&&!w.toolbar&&w.toolbarStyle==NSWindowToolbarStyleAutomatic);[w release];
 }else{
 void *h=vf_header_host_create(w,44,20,64);REQUIRE(h&&vf_header_host_state(h)==1&&vf_header_host_abi_version()==6);VFHeaderHost *o=h;
 REQUIRE(o->_view.isFlipped&&o->_carrier->_view==o->_view&&o->_view.fittingSize.height==44);
 REQUIRE(vf_header_host_set_height(h,44)&&!vf_header_host_set_height(h,32));
 if([test isEqual:@"callback"]){
 unsigned calls=0;REQUIRE(vf_header_host_set_change_callback(h,changedNow,&calls));
 [o changed:[NSNotification notificationWithName:NSWindowWillEnterFullScreenNotification object:w]];
 REQUIRE(calls==1); // FD was already pending from construction.
 [o changed:[NSNotification notificationWithName:NSWindowDidEnterFullScreenNotification object:w]];
 REQUIRE(calls==2);[o signal];REQUIRE(calls==2);
 o->_view.frame=NSMakeRect(10,12,1000,44);REQUIRE(calls==3);
 [o->_view setFrameOrigin:NSMakePoint(20,12)];REQUIRE(calls==4);
 [o->_view setFrameSize:NSMakeSize(1010,44)];REQUIRE(calls==5);
 REQUIRE(vf_header_host_set_change_callback(h,NULL,NULL));
 [o changed:[NSNotification notificationWithName:NSWindowWillExitFullScreenNotification object:w]];REQUIRE(calls==5);
 }
 if([test isEqual:@"brand_restore"]||[test isEqual:@"brand_external"]){
   w.backgroundColor=NSColor.blackColor;brandWindow=(NSWindow *)w;
   object_setClass(o->_view,VFBrandView.class);
   REQUIRE(vf_header_host_set_background(h,.188,.169,.227,1));
   REQUIRE([w.backgroundColor isEqual:o->_view->_brandColor]&&o->_paintWindows.count==1);
   if([test isEqual:@"brand_external"])w.backgroundColor=NSColor.redColor;
   object_setClass(o->_view,VFHeaderContainer.class);brandWindow=nil;
 }
 if([test isEqual:@"brand"]){
 REQUIRE(vf_header_host_set_background(h,0.188,0.169,0.227,1));
 REQUIRE(o->_view->_brandColor);
 NSBitmapImageRep *bitmap=[[[NSBitmapImageRep alloc]initWithBitmapDataPlanes:NULL pixelsWide:64 pixelsHigh:44 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0]autorelease];
 [NSGraphicsContext saveGraphicsState];[NSGraphicsContext setCurrentContext:[NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap]];
 [o->_view drawRect:NSMakeRect(0,0,64,44)];[NSGraphicsContext restoreGraphicsState];
 NSColor *pixel=[[bitmap colorAtX:32 y:22]colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
 REQUIRE(fabs(pixel.redComponent-.188)<.01&&fabs(pixel.greenComponent-.169)<.01&&fabs(pixel.blueComponent-.227)<.01);
 REQUIRE(!vf_header_host_set_background(h,2,0,0,1)&&!vf_header_host_set_background(h,0,0,0,0));
 }
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
 if([test isEqual:@"callback_retire"]){
   object_setClass(o,VFCallbackHost.class);REQUIRE(vf_header_host_set_change_callback(h,retireNow,&h));
   [o changed:[NSNotification notificationWithName:NSWindowWillEnterFullScreenNotification object:w]];
   REQUIRE(!h&&!w.toolbar);goto doneWithOwner;
 }
 int fd=vf_header_host_event_fd(h);REQUIRE(fd>=0);
 REQUIRE(vf_header_host_destroy(&h)&&!h&&!w.toolbar&&w.toolbarStyle==NSWindowToolbarStyleAutomatic&&w.delegate==delegate);
 if([test isEqual:@"brand_restore"])REQUIRE([w.backgroundColor isEqual:NSColor.blackColor]);
 if([test isEqual:@"brand_external"])REQUIRE([w.backgroundColor isEqual:NSColor.redColor]);
 REQUIRE(fcntl(fd,F_GETFD)==-1&&errno==EBADF);REQUIRE(vf_header_host_destroy(&h));
 doneWithOwner:[w release];}
 REQUIRE(NSApp==nil);printf("{\"case\":\"%s\",\"passed\":true,\"nsapp_created\":false}\n",argv[1]);
}return 0;}
