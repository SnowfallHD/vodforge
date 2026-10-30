#import <AppKit/AppKit.h>
#import <QuartzCore/QuartzCore.h>
#include <stdio.h>

// Model public display/view properties only; exercise the production reader
// without creating NSApplication, an NSWindow, or synthetic OS input.
static NSArray *VFScreenFixtures;
@interface VFScreenFixture : NSObject
@property NSRect frame;
+ (NSArray *)screens;
@end
@implementation VFScreenFixture
+ (NSArray *)screens{return VFScreenFixtures;}
@end
#define NSScreen VFScreenFixture
#import "../../yt_downloader/platforms/macos/header_toolbar.m"
#undef NSScreen

@interface VFScreenTestWindow : NSObject
@end
@implementation VFScreenTestWindow
- (BOOL)isVisible{return YES;}
- (CGFloat)alphaValue{return 1;}
- (NSRect)convertRectToScreen:(NSRect)rect{return rect;}
@end
@interface VFScreenTestView : NSObject
@property NSRect screenRect;
@property CGFloat alphaValue;
@property BOOL hidden;
@end
@implementation VFScreenTestView
- (NSWindow *)window{static VFScreenTestWindow *window=nil;if(!window)window=[VFScreenTestWindow new];return (NSWindow *)window;}
- (NSView *)superview{return nil;}
- (CALayer *)layer{return nil;}
- (NSRect)bounds{return NSMakeRect(0,0,self.screenRect.size.width,self.screenRect.size.height);}
- (NSRect)visibleRect{return self.bounds;}
- (BOOL)isHiddenOrHasHiddenAncestor{return self.hidden;}
- (NSRect)convertRect:(NSRect)rect toView:(NSView *)view{(void)view;rect.origin.x+=self.screenRect.origin.x;rect.origin.y+=self.screenRect.origin.y;return rect;}
@end
static VFScreenFixture *screen(CGFloat x,CGFloat y,CGFloat w,CGFloat h) {
    VFScreenFixture *value=[[[VFScreenFixture alloc]init]autorelease];value.frame=NSMakeRect(x,y,w,h);return value;
}
static void printVisibility(VFScreenTestView *view) {
    NSRect bounds;unsigned state=VFVisibleRect((NSView *)view,&bounds);
    printf("{\"status\":%u,\"bounds\":[%.17g,%.17g,%.17g,%.17g]}",
        state,bounds.origin.x,bounds.origin.y,bounds.size.width,bounds.size.height);
}
int main(int argc,char **argv){@autoreleasepool{
    if(NSApp!=nil||argc!=2)return 9;
    NSString *test=@(argv[1]);
    VFScreenFixtures=@[screen(0,0,100,100),screen(100,0,100,100)];
    VFScreenTestView *view=[[[VFScreenTestView alloc]init]autorelease];
    view.alphaValue=1;view.screenRect=NSMakeRect(70,20,60,44);
    if([test isEqual:@"single"])view.screenRect=NSMakeRect(70,20,20,44);
    else if([test isEqual:@"adjacent-reversed"])VFScreenFixtures=@[screen(100,0,100,100),screen(0,0,100,100)];
    else if([test isEqual:@"vertical-negative"]){VFScreenFixtures=@[screen(-100,-100,100,100),screen(-100,0,100,100)];view.screenRect=NSMakeRect(-80,-20,44,60);}
    else if([test isEqual:@"mirrored"]){VFScreenFixtures=@[screen(0,0,100,100),screen(0,0,100,100)];view.screenRect=NSMakeRect(20,20,60,44);}
    else if([test isEqual:@"overlap"]){VFScreenFixtures=@[screen(0,0,100,100),screen(50,0,100,100)];view.screenRect=NSMakeRect(40,20,80,44);}
    else if([test isEqual:@"gap"]){VFScreenFixtures=@[screen(0,0,100,100),screen(120,0,100,100)];view.screenRect=NSMakeRect(70,20,80,44);}
    else if([test isEqual:@"inside-gap"]){VFScreenFixtures=@[screen(0,0,100,100),screen(120,0,100,100)];view.screenRect=NSMakeRect(105,20,10,44);}
    else if([test isEqual:@"staggered"]){VFScreenFixtures=@[screen(0,0,100,100),screen(100,50,100,100)];view.screenRect=NSMakeRect(70,-20,60,84);}
    else if([test isEqual:@"offscreen"])view.screenRect=NSMakeRect(250,20,20,44);
    else if([test isEqual:@"clipped"])view.screenRect=NSMakeRect(-20,20,60,44);
    else if([test isEqual:@"no-screens"])VFScreenFixtures=@[];
    else if([test isEqual:@"alpha-zero"])view.alphaValue=0;
    else if([test isEqual:@"hidden"])view.hidden=YES;
    else if([test isEqual:@"packet"]){
        VFScreenFixtures=@[screen(0,0,50,100),screen(50,0,150,100)];
        view.screenRect=NSMakeRect(0,40,180,44);printf("{\"host\":");printVisibility(view);printf(",\"buttons\":[");
        for(unsigned i=0;i<3;i++){if(i)printf(",");view.screenRect=NSMakeRect(20+23*i,55,14,14);printVisibility(view);}
        printf("],\"nsapp_nil\":%s}\n",NSApp==nil?"true":"false");return 0;
    }else if(![test isEqual:@"adjacent"])return 8;
    printf("{\"visibility\":");printVisibility(view);printf(",\"nsapp_nil\":%s}\n",NSApp==nil?"true":"false");
}return 0;}
