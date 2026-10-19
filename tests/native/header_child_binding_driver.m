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
 w.releasedWhenClosed=NO;w.titlebarAppearsTransparent=YES;w.titleVisibility=NSWindowTitleHidden;return w;
}
static void *owner(NSWindow *w){
 void *h=vf_header_host_create(w,44,12,300);CHECK(h);
 VFHeaderHost *o=h;
 // Hidden component fixture: give the exact item view its real native window
 // without ordering/activating or pretending toolbar allocation was tested.
 [w.contentView addSubview:o->_view];o->_view.frame=NSMakeRect(0,680,1000,44);
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
typedef struct {void **handle;TestChild *child;unsigned delivered;BOOL retire;VFHeaderPointerSnapshot last;} PointerObserver;
static void pointerChanged(void *context){
 PointerObserver *o=context;VFHeaderPointerSnapshot sample;
 if(vf_header_host_pointer_snapshot(*o->handle,&sample)!=1)return;
 if(sample.sequence==o->last.sequence)return;
 o->last=sample;o->delivered++;
 if(o->retire){CHECK(vf_header_host_unbind_child(*o->handle,o->child));CHECK(vf_header_host_destroy(o->handle));}
}
static NSEvent *pointerEvent(NSWindow *w,NSView *child,NSPoint local,NSEventType type){
 NSPoint location=[child convertPoint:local toView:nil];
 if(type!=NSEventTypeMouseEntered&&type!=NSEventTypeMouseExited)return [NSEvent mouseEventWithType:type location:location modifierFlags:0 timestamp:1.25 windowNumber:w.windowNumber context:nil eventNumber:1 clickCount:0 pressure:0];
 return [NSEvent enterExitEventWithType:type location:location modifierFlags:0 timestamp:1.25 windowNumber:w.windowNumber context:nil eventNumber:1 trackingNumber:0 userData:NULL];
}
static BOOL ready(void *h){return (vf_header_host_flags(h)&(1|256|512|1024))==(1|256|512|1024);}
int main(int argc,const char **argv){NSAutoreleasePool *pool=[NSAutoreleasePool new];
 CHECK(argc==2);[NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];CHECK(!NSApp.active);
 NSWindow *w=window();void *h=owner(w);NSRect r=NSMakeRect(96,4,900,44);
 if(!strcmp(argv[1],"negative_offset"))r=NSMakeRect(-24,-8,900,44);
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
  if(!strcmp(argv[1],"passive_tracking_registration")){
   // The native toolbar must own one passive tracking route even when Qt's
   // logical main parent differs from the AppKit fullscreen toolbar window.
   CHECK(c.trackingAreas.count==1);
   NSTrackingArea *area=c.trackingAreas[0];
   CHECK((area.options&(NSTrackingMouseMoved|NSTrackingMouseEnteredAndExited|NSTrackingInVisibleRect|NSTrackingActiveInActiveApp))
     ==(NSTrackingMouseMoved|NSTrackingMouseEnteredAndExited|NSTrackingInVisibleRect|NSTrackingActiveInActiveApp));
   CHECK(area.owner==o->_childBinding);
   CHECK(vf_header_host_unbind_child(h,c));CHECK(c.trackingAreas.count==0);
  }else if(!strcmp(argv[1],"passive_pointer_mapping")||!strcmp(argv[1],"passive_pointer_retire_callback")){
   PointerObserver observer={.handle=&h,.child=c,.retire=!strcmp(argv[1],"passive_pointer_retire_callback")};
   CHECK(vf_header_host_pointer_snapshot_size()==sizeof(VFHeaderPointerSnapshot));
   CHECK(vf_header_host_set_change_callback(h,pointerChanged,&observer));
   NSWindow *overlay=window();
   NSRect rects[]={r,NSMakeRect(-24,-8,900,44),NSMakeRect(99,4,900,44),r};
   for(unsigned phase=0;phase<4;phase++){
    if(phase==1)[overlay.contentView addSubview:o->_view];
    if(phase==3)[w.contentView addSubview:o->_view];
    c.frame=rects[phase];CHECK(vf_header_host_update_child(h,c,c.frame.origin.x,c.frame.origin.y,c.frame.size.width,c.frame.size.height));
    CHECK(vf_header_host_drain(h)>=0);
    VFHeaderChildBinding *binding=o->_childBinding;NSPoint point=NSMakePoint(123.25,22.5);
    [binding mouseEntered:pointerEvent(c.window,c,point,NSEventTypeMouseEntered)];
    CHECK(observer.last.child==(uintptr_t)c&&observer.last.kind==1&&observer.last.timestamp==1.25);
    if(h)CHECK(vf_header_host_drain(h)==0);
    CHECK(fabs(observer.last.x-point.x)<.001&&fabs(observer.last.y-point.y)<.001);
    if(observer.retire){CHECK(!h&&c.trackingAreas.count==0);break;}
    unsigned before=observer.delivered;
    [binding mouseMoved:pointerEvent(c.window,c,NSMakePoint(300,20),NSEventTypeMouseMoved)];
    CHECK(observer.delivered==before+1&&observer.last.kind==2&&observer.last.x==300);
    // Wrong native window, outside entry/move, and action types cannot admit.
    before=observer.delivered;
    [binding mouseMoved:pointerEvent(c.window==w?overlay:w,c,point,NSEventTypeMouseMoved)];
    [binding mouseMoved:pointerEvent(c.window,c,NSMakePoint(-10,20),NSEventTypeMouseMoved)];
    [binding mouseMoved:pointerEvent(c.window,c,point,NSEventTypeLeftMouseDown)];
    CHECK(observer.delivered==before);
    [binding mouseExited:pointerEvent(c.window,c,NSMakePoint(-10,20),NSEventTypeMouseExited)];
    CHECK(observer.delivered==before+1&&observer.last.kind==3&&observer.last.x==-10);
   }
   if(h)CHECK(vf_header_host_set_change_callback(h,NULL,NULL));
   [overlay close];[overlay release];
  }else if(!strcmp(argv[1],"hit_mapping")){
   NSRect rects[]={r,NSMakeRect(-24,-8,900,44),NSMakeRect(0,-52,1050,44),NSMakeRect(99,4,900,44),r};
   for(unsigned phase=0;phase<5;phase++){
    NSRect next=rects[phase];o->_view.frame=NSMakeRect(0,680,next.size.width,44);c.frame=next;
    CHECK(vf_header_host_update_child(h,c,next.origin.x,next.origin.y,next.size.width,next.size.height)&&ready(h));
    CGFloat xs[]={2,100,250,450,next.size.width-45,next.size.width-5};
    for(unsigned i=0;i<6;i++){
     NSPoint local=NSMakePoint(xs[i],25);
     NSPoint inHost=[o->_view convertPoint:local fromView:c];
     CHECK(fabs(inHost.x-local.x)<.02&&fabs(inHost.y-local.y)<.02);
     NSPoint parent=[o->_view.superview convertPoint:local fromView:c];
     NSView *hit=[o->_view hitTest:parent];
     if(hit!=c)fprintf(stderr,"hit phase=%u x=%g parent=%s host=%s container=%s bounds=%s child=%s hidden=%d/%d/%d hit=%s\n",phase,(double)xs[i],NSStringFromPoint(parent).UTF8String,NSStringFromRect(o->_view.frame).UTF8String,NSStringFromRect(container.frame).UTF8String,NSStringFromRect(container.bounds).UTF8String,NSStringFromRect(c.frame).UTF8String,o->_view.hidden,container.hidden,c.hidden,hit.description.UTF8String);
     CHECK(hit==c);
     NSPoint screen=[c.window convertPointToScreen:[c convertPoint:local toView:nil]];
     NSPoint windowPoint=[c.window convertPointFromScreen:screen];
     NSPoint eventLocal=[c convertPoint:windowPoint fromView:nil];
     CHECK(fabs(eventLocal.x-local.x)<.02&&fabs(eventLocal.y-local.y)<.02);
    }
   }
  }else if(!strcmp(argv[1],"same_resize")){
   NSRect old=container.frame;o->_view.frame=NSMakeRect(0,670,1050,44);[o->_view resizeSubviewsWithOldSize:NSMakeSize(1000,44)];
   CHECK(NSEqualRects(container.frame,old)&&c->frameWrites==writes&&ready(h));
  }else if(!strcmp(argv[1],"update_and_mismatch")){
   NSRect next=NSMakeRect(30,-6,820,44);c.frame=next;unsigned after=c->frameWrites;
   CHECK(vf_header_host_update_child(h,c,30,-6,820,44)&&ready(h)&&c->frameWrites==after);
   NSRect before=container.frame;CHECK(!vf_header_host_update_child(h,c,31,-6,820,44));CHECK(NSEqualRects(before,container.frame)&&c->frameWrites==after);
   TestChild *other=child(w,r);CHECK(!vf_header_host_update_child(h,other,30,-6,820,44)&&other.superview==w.contentView);[other removeFromSuperview];[other release];
  }else if(!strcmp(argv[1],"update_exception_rollback")){
   NSRect before=container.frame,bounds=container.bounds;NSRect next=NSMakeRect(32,-7,800,44);c.frame=next;unsigned after=c->frameWrites;
   Method m=class_getInstanceMethod(VFHeaderOffsetContainer.class,@selector(setFrame:));originalFrame=method_getImplementation(m);method_setImplementation(m,(IMP)failFrame);throwContainer=YES;
   CHECK(!vf_header_host_update_child(h,c,32,-7,800,44));method_setImplementation(m,originalFrame);
   CHECK(NSEqualRects(container.frame,before)&&NSEqualRects(container.bounds,bounds)&&NSEqualRects(c.frame,next)&&c->frameWrites==after);
   CHECK(vf_header_host_update_child(h,c,32,-7,800,44)&&ready(h));
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
