#import <AppKit/AppKit.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#import <objc/runtime.h>
#define CHECK(c) do{if(!(c)){fprintf(stderr,"failed:%s:%d\n",#c,__LINE__);exit(3);}}while(0)
#import "../../yt_downloader/platforms/macos/header_toolbar.m"
static unsigned childDeallocations;
@interface TestChild:NSView {
@public unsigned frameWrites;BOOL throwFlagEnable,throwFlagRestore,flagValue;
}
@end
@implementation TestChild
- (void)dealloc{childDeallocations++;[super dealloc];}
- (BOOL)isFlipped{return YES;}
- (void)setFrame:(NSRect)r{frameWrites++;[super setFrame:r];}
- (BOOL)postsFrameChangedNotifications{return flagValue;}
- (void)setPostsFrameChangedNotifications:(BOOL)v {
 if(v&&throwFlagEnable){throwFlagEnable=NO;[NSException raise:@"fixture_flag_enable" format:@"static"];}
 if(!v&&throwFlagRestore){throwFlagRestore=NO;[NSException raise:@"fixture_flag_restore" format:@"static"];}
 flagValue=v;[super setPostsFrameChangedNotifications:v];
}
@end
static NSWindow *window(void){
 NSWindow *w=[[NSWindow alloc]initWithContentRect:NSMakeRect(0,0,1100,740) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable|NSWindowStyleMaskFullSizeContentView backing:NSBackingStoreBuffered defer:NO];
 w.releasedWhenClosed=NO;w.titlebarAppearsTransparent=YES;return w;
}
static void *owner(NSWindow *w){
 void *h=vf_header_host_create(w,50,12,300);CHECK(h);
 VFHeaderHost *o=h;
 // Hidden component fixture: give the exact item view its real native window
 // without ordering/activating or pretending toolbar allocation was tested.
 [w.contentView addSubview:o->_view];o->_view.frame=NSMakeRect(0,680,1000,50);
 CHECK(!w.visible&&vf_header_host_state(h)==1);return h;
}
static TestChild *child(NSWindow *w,NSRect r){TestChild *v=[[TestChild alloc]initWithFrame:r];[w.contentView addSubview:v];return v;}
static void finish(NSWindow *w,void **h,TestChild *c){
 if(*h&&((VFHeaderHost *)*h)->_childBinding)CHECK(vf_header_host_unbind_child(*h,c));
 CHECK(vf_header_host_destroy(h)&&!*h&&vf_header_host_destroy(h));
 CHECK(!w.visible&&!NSApp.active);[c release];[w close];[w release];
}
static IMP originalFrame;static BOOL throwContainer;
static void failFrame(id receiver,SEL selector,NSRect r){
 ((void(*)(id,SEL,NSRect))originalFrame)(receiver,selector,r);
 if(throwContainer&&((VFHeaderOffsetContainer *)receiver)->_binding){throwContainer=NO;[NSException raise:@"fixture_after_frame" format:@"static"];}
}
static BOOL ready(void *h){return (vf_header_host_flags(h)&(1|256|512|1024))==(1|256|512|1024);}
int main(int argc,const char **argv){NSAutoreleasePool *pool=[NSAutoreleasePool new];
 CHECK(argc==2);[NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];CHECK(!NSApp.active);
 NSWindow *w=window();void *h=owner(w);NSRect r=NSMakeRect(96,4,900,50);
 if(!strcmp(argv[1],"negative_offset"))r=NSMakeRect(-24,-8,900,50);
 TestChild *c=child(w,r);unsigned writes=c->frameWrites;
 if(!strcmp(argv[1],"partial_container_setter")){
  Method m=class_getInstanceMethod(VFHeaderOffsetContainer.class,@selector(setFrame:));originalFrame=method_getImplementation(m);method_setImplementation(m,(IMP)failFrame);throwContainer=YES;
  CHECK(!vf_header_host_bind_child(h,c,r.origin.x,r.origin.y,r.size.width,r.size.height));method_setImplementation(m,originalFrame);
  CHECK(!((VFHeaderHost *)h)->_childBinding&&c.superview==nil&&NSEqualRects(c.frame,r));
 }else if(!strcmp(argv[1],"partial_flag_enable")){
  c->throwFlagEnable=YES;CHECK(!vf_header_host_bind_child(h,c,r.origin.x,r.origin.y,r.size.width,r.size.height));
  CHECK(!((VFHeaderHost *)h)->_childBinding&&!c.postsFrameChangedNotifications&&c.superview==nil);
 }else{
  CHECK(vf_header_host_bind_child(h,c,r.origin.x,r.origin.y,r.size.width,r.size.height));CHECK(ready(h));
  CHECK(c->frameWrites==writes&&NSEqualRects(c.frame,r));
  VFHeaderHost *o=h;NSView *container=c.superview;
  if(!strcmp(argv[1],"same_resize")){
   NSRect old=container.frame;o->_view.frame=NSMakeRect(0,670,1050,50);[o->_view resizeSubviewsWithOldSize:NSMakeSize(1000,50)];
   CHECK(NSEqualRects(container.frame,old)&&c->frameWrites==writes&&ready(h));
  }else if(!strcmp(argv[1],"update_and_mismatch")){
   NSRect next=NSMakeRect(30,-6,820,50);c.frame=next;unsigned after=c->frameWrites;
   CHECK(vf_header_host_update_child(h,c,30,-6,820,50)&&ready(h)&&c->frameWrites==after);
   NSRect before=container.frame;CHECK(!vf_header_host_update_child(h,c,31,-6,820,50));CHECK(NSEqualRects(before,container.frame)&&c->frameWrites==after);
   TestChild *other=child(w,r);CHECK(!vf_header_host_update_child(h,other,30,-6,820,50)&&other.superview==w.contentView);[other removeFromSuperview];[other release];
  }else if(!strcmp(argv[1],"update_exception_rollback")){
   NSRect before=container.frame,bounds=container.bounds;NSRect next=NSMakeRect(32,-7,800,50);c.frame=next;unsigned after=c->frameWrites;
   Method m=class_getInstanceMethod(VFHeaderOffsetContainer.class,@selector(setFrame:));originalFrame=method_getImplementation(m);method_setImplementation(m,(IMP)failFrame);throwContainer=YES;
   CHECK(!vf_header_host_update_child(h,c,32,-7,800,50));method_setImplementation(m,originalFrame);
   CHECK(NSEqualRects(container.frame,before)&&NSEqualRects(container.bounds,bounds)&&NSEqualRects(c.frame,next)&&c->frameWrites==after);
   CHECK(vf_header_host_update_child(h,c,32,-7,800,50)&&ready(h));
  }else if(!strcmp(argv[1],"child_external_release_first")){
   @autoreleasepool{[c removeFromSuperview];TestChild *raw=c;[c release];c=nil;CHECK(childDeallocations==0);
   CHECK(vf_header_host_unbind_child(h,raw));}
   // NSView subviews snapshots from prior admission retain children until the fixture pool drains.

  }else if(!strcmp(argv[1],"foreign_reparent_fd")){
   CHECK(vf_header_host_drain(h)>=0);[w.contentView addSubview:c];
   CHECK(!(vf_header_host_flags(h)&512)&&vf_header_host_drain(h)>0);NSRect before=c.frame;void *saved=h;
   CHECK(!vf_header_host_update_child(h,c,r.origin.x,r.origin.y,r.size.width,r.size.height));CHECK(!vf_header_host_destroy(&h)&&h==saved&&c.superview==w.contentView&&NSEqualRects(before,c.frame));
   CHECK(vf_header_host_unbind_child(h,c));
  }else if(!strcmp(argv[1],"foreign_adoption_refused")){
   NSView *foreign=[[[NSView alloc]initWithFrame:NSMakeRect(0,0,100,100)]autorelease];[w.contentView addSubview:foreign];[foreign addSubview:c];
   CHECK(!vf_header_host_unbind_child(h,c)&&c.superview==foreign);[container addSubview:c];CHECK(vf_header_host_unbind_child(h,c));
  }else if(!strcmp(argv[1],"flag_restore_retry")){
   c->throwFlagRestore=YES;void *saved=h;CHECK(!vf_header_host_unbind_child(h,c));
   CHECK(c.superview==container&&h==saved&&!vf_header_host_destroy(&h)&&h==saved);
   CHECK(vf_header_host_unbind_child(h,c)&&!c.postsFrameChangedNotifications);
  }else if(!strcmp(argv[1],"child_detach_first")){
   [c removeFromSuperview];CHECK(!(vf_header_host_flags(h)&512));CHECK(vf_header_host_unbind_child(h,c));
  }else if(!strcmp(argv[1],"native_close_release_only")){
   [c removeFromSuperview];unsigned before=c->frameWrites;
   [[NSNotificationCenter defaultCenter]postNotificationName:NSWindowWillCloseNotification object:w];
   CHECK(vf_header_host_state(h)==-1&&vf_header_host_destroy(&h)&&!h&&c->frameWrites==before);
  }else CHECK(!strcmp(argv[1],"basic")||!strcmp(argv[1],"negative_offset"));
 }
 finish(w,&h,c);[pool drain];
 if(!strcmp(argv[1],"child_external_release_first"))CHECK(childDeallocations==1);
 printf("{\"case\":\"%s\",\"passed\":true,\"hidden\":true,\"inactive\":true}\n",argv[1]);return 0;
}
