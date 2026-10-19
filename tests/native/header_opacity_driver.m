#import <AppKit/AppKit.h>
#import <QuartzCore/QuartzCore.h>
#import "../../yt_downloader/platforms/macos/header_toolbar.m"
#include <stdio.h>
#define CHECK(c) do{if(!(c)){fprintf(stderr,"FAIL:%s line%d\n",#c,__LINE__);return 3;}}while(0)
@interface VFReadOnlyTestWindow:NSObject
@end
@implementation VFReadOnlyTestWindow
- (BOOL)isVisible{return YES;}
- (CGFloat)alphaValue{return 1;}
- (NSRect)convertRectToScreen:(NSRect)r{return r;}
@end
// Exact reader consumer with mocked public view/window properties only.
// No AppKit window/application is created; actual native provenance is separate.
@interface VFReadOnlyTestView:NSObject
@property CGFloat alphaValue;
@property BOOL hidden,wantsLayer;
@property(retain) NSView *superview;
@property(retain) CALayer *layer;
@end
@implementation VFReadOnlyTestView
- (instancetype)initWithFrame:(NSRect)r{(void)r;self=[super init];self.alphaValue=1;return self;}
- (NSWindow *)window{static VFReadOnlyTestWindow *w=nil;if(!w)w=[VFReadOnlyTestWindow new];return (NSWindow *)w;}
- (NSRect)bounds{return NSMakeRect(0,0,14,14);}
- (NSRect)visibleRect{return self.bounds;}
- (BOOL)isHiddenOrHasHiddenAncestor{return self.hidden||self.superview.hiddenOrHasHiddenAncestor;}
- (void)addSubview:(VFReadOnlyTestView *)child{child.superview=(NSView *)self;}
- (NSRect)convertRect:(NSRect)r toView:(NSView *)v{(void)v;r.origin.x+=20;r.origin.y+=860;return r;}
@end
@interface VFReadOnlyPresentationLayer:CALayer
@property(retain) CALayer *testPresentation;
@end
@implementation VFReadOnlyPresentationLayer
- (instancetype)presentationLayer{return (VFReadOnlyPresentationLayer *)self.testPresentation;}
@end
int main(int argc,char **argv){@autoreleasepool{
 CHECK(NSApp==nil);CHECK(argc==2);NSString *test=@(argv[1]);
 VFReadOnlyTestView *v=[[[VFReadOnlyTestView alloc]initWithFrame:NSMakeRect(0,0,14,14)]autorelease];NSRect clip;
 if([test isEqual:@"alpha_zero"]){v.alphaValue=0;CHECK(VFVisibleRect((NSView *)v,&clip)==2);CHECK(NSIsEmptyRect(clip));}
 if([test isEqual:@"ancestor_zero"]){VFReadOnlyTestView *parent=[[[VFReadOnlyTestView alloc]initWithFrame:NSMakeRect(0,0,100,100)]autorelease];[parent addSubview:v];parent.alphaValue=0;CHECK(VFVisibleRect((NSView *)v,&clip)==2);}
 if([test isEqual:@"layer_zero"]){v.layer=[CALayer layer];v.wantsLayer=YES;v.layer.opacity=0;CHECK(VFVisibleRect((NSView *)v,&clip)==2);}
 if([test isEqual:@"presentation_positive"]){VFReadOnlyPresentationLayer *l=[VFReadOnlyPresentationLayer layer];l.opacity=0;l.testPresentation=[CALayer layer];l.testPresentation.opacity=.5;v.layer=l;v.wantsLayer=YES;v.alphaValue=0;CHECK(VFVisibleRect((NSView *)v,&clip)==1);CHECK(!NSIsEmptyRect(clip));}
 if([test isEqual:@"presentation_zero"]){VFReadOnlyPresentationLayer *l=[VFReadOnlyPresentationLayer layer];l.testPresentation=[CALayer layer];l.testPresentation.opacity=0;v.layer=l;v.wantsLayer=YES;CHECK(VFVisibleRect((NSView *)v,&clip)==2);}
 if([test isEqual:@"positive"]){CHECK(VFVisibleRect((NSView *)v,&clip)==1);}
 CHECK(NSApp==nil);printf("PASS %s NSApp=nil\n",argv[1]);
}return 0;}
