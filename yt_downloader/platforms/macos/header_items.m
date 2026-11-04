// VODForge's macOS header as real AppKit toolbar items.
//
// Each control (brand, navigation, search, X, Settings) is its own NSToolbarItem
// drawn by AppKit. AppKit therefore lays out and moves every control in the
// same transaction as the window, menu bar and window buttons: nothing is
// redrawn late by another renderer, and nothing infers where AppKit will move
// the toolbar. Qt keeps ownership of every action: this file only reports
// what the user did through a queued event pipe; Python applies it.
#import <AppKit/AppKit.h>
#include <fcntl.h>
#include <math.h>
#include <string.h>
#include <unistd.h>

@class VFTBHeader;
static NSString *const VFTBBrandID = @"org.vodforge.header.brand";
static NSString *const VFTBSearchID = @"org.vodforge.header.search";
static NSString *const VFTBXID = @"org.vodforge.header.x";
static NSString *const VFTBSettingsID = @"org.vodforge.header.settings";
static NSString *const VFTBNavPrefix = @"org.vodforge.header.nav.";
// Clearance between AppKit's window buttons and the mark, matching the Qt header.
static const CGFloat VFTBBrandLeading = 4;
static NSArray *VFTBNavNames(void) { return @[@"Forge", @"Library", @"Watch", @"Activity"]; }

@interface VFTBHeader : NSObject <NSToolbarDelegate, NSTextFieldDelegate> {
@public
    NSWindow *_window;            // retained main window
    NSToolbar *_toolbar;
    NSString *_assets;
    NSMutableDictionary *_colors;     // role -> NSColor
    NSMutableDictionary *_materials;  // name -> NSImage (nine-part)
    NSMutableDictionary *_icons;      // file name -> NSImage
    NSMutableArray *_events;          // JSON strings
    NSMutableDictionary *_buttons;    // identifier -> VFTBButton
    NSView *_brand, *_searchBox, *_backdrop, *_catcher;
    NSArray *_dim;  // NSColor layers Qt's modal popups currently paint over the window
    NSTextField *_searchField;
    NSToolbarItem *_searchItem;
    NSString *_selection;
    NSWindowToolbarStyle _oldStyle;
    NSTitlebarSeparatorStyle _oldSeparator;
    int _pipe[2];
    BOOL _closed, _searchVisible, _compact, _layoutQueued;
    int _transition;  // 1 entering, 2 exiting fullscreen, 0 otherwise
}
- (void)emit:(NSString *)kind value:(NSString *)value;
- (NSColor *)color:(NSString *)role;
- (NSImage *)material:(NSString *)name;
- (NSImage *)icon:(NSString *)file;
- (void)activate:(NSString *)identifier;
- (void)hover:(NSString *)identifier inside:(BOOL)inside;
- (void)installBackdrop;
- (BOOL)dimmed;
- (void)applyDim:(NSRect)rect;
- (void)outsidePress;
- (void)installCatcher;
@end

static NSFont *VFTBFont(CGFloat size, BOOL bold) {
    NSFont *font = [NSFont fontWithName:bold ? @"HelveticaNeue-Bold" : @"HelveticaNeue" size:size];
    return font ?: (bold ? [NSFont boldSystemFontOfSize:size] : [NSFont systemFontOfSize:size]);
}

// The same line icons as SceneIcon.qml: unit coordinates, 2pt round strokes,
// clipped to the icon square exactly like the Canvas they replace.
static void VFTBStrokeIcon(NSString *name, NSRect r, NSColor *tone) {
    CGFloat s = MIN(NSWidth(r), NSHeight(r)), ox = NSMinX(r), oy = NSMinY(r);
    NSBezierPath *path = [NSBezierPath bezierPath];
    void (^line)(const CGFloat *, int) = ^(const CGFloat *p, int count) {
        [path moveToPoint:NSMakePoint(ox + p[0] * s, oy + p[1] * s)];
        for (int i = 1; i < count; i++) [path lineToPoint:NSMakePoint(ox + p[2 * i] * s, oy + p[2 * i + 1] * s)];
    };
    if ([name isEqual:@"download"]) {
        static const CGFloat a[] = {.5, 0, .5, .70}, b[] = {.25, .45, .5, .70, .75, .45}, c[] = {0, .65, 0, 1, 1, 1, 1, .65};
        line(a, 2); line(b, 3); line(c, 4);
    } else if ([name isEqual:@"folder"]) {
        static const CGFloat a[] = {0, .22, .35, .22, .48, .38, 1, .38, 1, .94, 0, .94, 0, .22};
        line(a, 7);
    } else if ([name isEqual:@"play"]) {
        static const CGFloat a[] = {.25, .12, .82, .5, .25, .88, .25, .12};
        line(a, 4);
    } else if ([name isEqual:@"activity"]) {
        static const CGFloat a[] = {.08, .53, .28, .53, .39, .22, .58, .81, .72, .47, .92, .47};
        line(a, 6);
    } else if ([name isEqual:@"x"]) {
        static const CGFloat a[] = {.08, .08, .31, .08, .92, .92, .69, .92, .08, .08}, b[] = {.86, .08, .08, .92};
        line(a, 5); [path closePath]; line(b, 2);
    } else {
        return;
    }
    path.lineWidth = 2;
    path.lineJoinStyle = NSLineJoinStyleRound;
    path.lineCapStyle = NSLineCapStyleRound;
    [NSGraphicsContext saveGraphicsState];
    NSRectClip(r);
    [tone setStroke];
    [path stroke];
    [NSGraphicsContext restoreGraphicsState];
}

static void VFTBDrawTinted(NSImage *image, NSRect r, NSColor *tone) {
    if (!image) return;
    NSImage *tinted = [NSImage imageWithSize:r.size flipped:NO drawingHandler:^BOOL(NSRect d) {
        [image drawInRect:d fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1];
        [tone set];
        NSRectFillUsingOperation(d, NSCompositingOperationSourceIn);
        return YES;
    }];
    [tinted drawInRect:r fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1
        respectFlipped:YES hints:nil];
}

// Shared Qt materials are drawn in flipped (top-down) views. NSImage's nine-part
// drawing ignores respectFlipped, so unflip locally: otherwise the material's
// lighting renders upside down (raised faces look sunken, shadows on top).
static void VFTBDrawMaterial(NSImage *image, NSRect r, BOOL flipped) {
    if (!image || NSIsEmptyRect(r)) return;
    [NSGraphicsContext saveGraphicsState];
    if (flipped) {
        NSAffineTransform *t = [NSAffineTransform transform];
        [t translateXBy:0 yBy:NSMinY(r) + NSMaxY(r)];
        [t scaleXBy:1 yBy:-1];
        [t concat];
    }
    [image drawInRect:r fromRect:NSZeroRect operation:NSCompositingOperationSourceOver fraction:1];
    [NSGraphicsContext restoreGraphicsState];
}

// While Qt shows a modal popup, its dimmer covers the window but not AppKit's
// toolbar. Darken what each header view drew (source-atop: transparent padding
// stays transparent, so the Qt-dimmed background behind it is not dimmed twice).
static void VFTBDimDrawn(NSArray *layers, NSRect rect) {
    for (NSColor *layer in layers) {
        [layer setFill];
        NSRectFillUsingOperation(rect, NSCompositingOperationSourceAtop);
    }
}

#pragma mark - Button

@interface VFTBButton : NSView {
@public
    VFTBHeader *_header;  // owner, not retained
    NSString *_identifier, *_label, *_icon;
    BOOL _selected, _quiet, _hovered, _pressed, _imageIcon;
    // AppKit places toolbar items edge to edge; the Qt header's Row spacing
    // lives here as transparent padding around the button face.
    CGFloat _leading, _trailing;
}
@end

@implementation VFTBButton
- (NSRect)face {
    NSRect b = self.bounds;
    return NSMakeRect(_leading, 0, MAX(0, NSWidth(b) - _leading - _trailing), NSHeight(b));
}
- (BOOL)isFlipped { return YES; }
- (BOOL)mouseDownCanMoveWindow { return NO; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { (void)event; return YES; }
- (BOOL)acceptsFirstResponder { return NSApp.isFullKeyboardAccessEnabled; }
- (BOOL)canBecomeKeyView { return NSApp.isFullKeyboardAccessEnabled; }
- (void)dealloc { [_identifier release]; [_label release]; [_icon release]; [super dealloc]; }
- (NSDictionary *)labelAttributes {
    BOOL accent = _selected;
    return @{NSFontAttributeName: VFTBFont(15, NO),
             NSForegroundColorAttributeName: [_header color:accent ? @"accent" : @"text"]};
}
- (NSSize)intrinsicContentSize {
    if (!_label.length) return NSMakeSize(_leading + 28 + _trailing, 40);
    CGFloat text = ceil([_label sizeWithAttributes:[self labelAttributes]].width);
    // StoneButton: max(86, 2 * padding + caption + icon + spacing), default height.
    return NSMakeSize(_leading + MAX(86, 2 * 16 + text + 18 + 8) + _trailing, 44);
}
- (void)updateTrackingAreas {
    [super updateTrackingAreas];
    for (NSTrackingArea *area in self.trackingAreas) [self removeTrackingArea:area];
    NSTrackingArea *area = [[NSTrackingArea alloc] initWithRect:[self face]
        options:NSTrackingMouseEnteredAndExited | NSTrackingActiveInActiveApp
          owner:self userInfo:nil];
    [self addTrackingArea:area];
    [area release];
}
- (void)setHovered:(BOOL)hovered {
    if (hovered && [_header dimmed]) hovered = NO;  // inactive behind a modal popup
    if (_hovered == hovered) return;
    _hovered = hovered;
    self.needsDisplay = YES;
    [_header hover:_identifier inside:hovered];
}
- (void)mouseEntered:(NSEvent *)event { (void)event; [self setHovered:YES]; }
- (void)mouseExited:(NSEvent *)event { (void)event; [self setHovered:NO]; }
- (void)viewDidMoveToWindow { [super viewDidMoveToWindow]; if (!self.window) [self setHovered:NO]; }
- (BOOL)inside:(NSEvent *)event {
    return NSPointInRect([self convertPoint:event.locationInWindow fromView:nil], [self face]);
}
- (NSView *)hitTest:(NSPoint)point {
    // Padding between controls belongs to the toolbar (window drag), not the button.
    NSPoint local = [self convertPoint:point fromView:self.superview];
    return NSPointInRect(local, [self face]) ? self : nil;
}
- (void)mouseDown:(NSEvent *)event { _pressed = [self inside:event]; self.needsDisplay = YES; }
- (void)mouseDragged:(NSEvent *)event {
    BOOL pressed = [self inside:event];
    if (pressed != _pressed) { _pressed = pressed; self.needsDisplay = YES; }
}
- (void)mouseUp:(NSEvent *)event {
    BOOL activate = _pressed && [self inside:event];
    _pressed = NO;
    self.needsDisplay = YES;
    if (activate) [_header activate:_identifier];
}
- (void)keyDown:(NSEvent *)event {
    if ([_header dimmed]) return;  // inactive behind a modal popup
    if ([event.charactersIgnoringModifiers isEqual:@" "] || [event.charactersIgnoringModifiers isEqual:@"\r"])
        [_header activate:_identifier];
    else
        [super keyDown:event];
}
- (NSRect)focusRingMaskBounds { return [self face]; }
- (void)drawFocusRingMask {
    [[NSBezierPath bezierPathWithRoundedRect:NSInsetRect([self face], 5, 5) xRadius:8 yRadius:8] fill];
}
- (void)drawRect:(NSRect)dirty {
    (void)dirty;
    NSRect bounds = [self face];
    BOOL pressed = _pressed || (_selected && _label.length);
    if (!_quiet || _hovered || _pressed) {
        NSImage *face = [_header material:pressed ? @"button-pressed" : _hovered ? @"button-hover" : @"button-normal"];
        VFTBDrawMaterial(face, bounds, self.isFlipped);
    }
    NSColor *tone = _selected ? [_header color:@"selection"] : [_header color:@"icon"];
    CGFloat contentWidth = 18;
    NSDictionary *attributes = nil;
    if (_label.length) {
        attributes = [self labelAttributes];
        contentWidth += 8 + [_label sizeWithAttributes:attributes].width;
    }
    // Quiet controls align their icon 8pt from the leading edge (StoneButton).
    CGFloat x = NSMinX(bounds) + (_quiet ? 8 : round((NSWidth(bounds) - contentWidth) / 2));
    NSRect icon = NSMakeRect(x, round(NSMidY(bounds) - 9), 18, 18);
    if (_imageIcon) VFTBDrawTinted([_header icon:_icon], icon, tone);
    else VFTBStrokeIcon(_icon, icon, tone);
    if (attributes) {
        NSSize size = [_label sizeWithAttributes:attributes];
        [_label drawAtPoint:NSMakePoint(x + 26, round(NSMidY(bounds) - size.height / 2))
             withAttributes:attributes];
    }
    [_header applyDim:self.bounds];
}
- (BOOL)isAccessibilityElement { return YES; }
- (NSAccessibilityRole)accessibilityRole { return NSAccessibilityButtonRole; }
- (NSString *)accessibilityLabel {
    if (_label.length) return _label;
    return [_identifier isEqual:VFTBXID] ? @"VODForge on X" : @"Settings";
}
- (BOOL)isAccessibilitySelected { return _selected; }
- (BOOL)accessibilityPerformPress {
    // Behind a modal popup this is a press on the dimmed background, like a click.
    if ([_header dimmed]) [_header outsidePress];
    else [_header activate:_identifier];
    return YES;
}
- (BOOL)isAccessibilityEnabled { return ![_header dimmed]; }
@end

#pragma mark - Brand

@interface VFTBBrand : NSView {
@public
    VFTBHeader *_header;
}
@end
@implementation VFTBBrand
- (BOOL)isFlipped { return YES; }
- (NSSize)intrinsicContentSize {
    // Qt: navigation starts brandWidth (46 or 150) + 4 or 3 after the mark.
    return NSMakeSize(VFTBBrandLeading + (_header->_compact ? 50 : 153), 44);
}
- (void)viewDidMoveToWindow {
    [super viewDidMoveToWindow];
    [_header installBackdrop];
    [_header installCatcher];
}
- (void)drawRect:(NSRect)dirty {
    (void)dirty;
    NSImage *mark = [_header icon:@"brand/vf-mark.png"];
    // Canonical lockup from Main.qml: 36pt mark, 13/191 gap less export padding.
    CGFloat w = 36 * 468.0 / 410, gap = (36 * 400.0 / 410) * 13 / 191 - 36 * 8.0 / 410;
    [mark drawInRect:NSMakeRect(VFTBBrandLeading, 4, w, 36) fromRect:NSZeroRect operation:NSCompositingOperationSourceOver
            fraction:1 respectFlipped:YES hints:nil];
    if (_header->_compact) { [_header applyDim:self.bounds]; return; }
    NSMutableAttributedString *text = [[NSMutableAttributedString alloc] initWithString:@"VODForge"
        attributes:@{NSFontAttributeName: VFTBFont(19, YES), NSForegroundColorAttributeName: [NSColor whiteColor]}];
    [text addAttribute:NSForegroundColorAttributeName value:[_header color:@"accent"] range:NSMakeRange(0, 3)];
    [text drawAtPoint:NSMakePoint(VFTBBrandLeading + w + gap, round(22 - text.size.height / 2))];
    [text release];
    [_header applyDim:self.bounds];
}
- (BOOL)isAccessibilityElement { return YES; }
- (NSAccessibilityRole)accessibilityRole { return NSAccessibilityStaticTextRole; }
- (NSString *)accessibilityLabel { return @"VODForge"; }
@end

#pragma mark - Search

@interface VFTBSearchField : NSTextField {
@public
    VFTBHeader *_header;
}
@end
@implementation VFTBSearchField
- (BOOL)becomeFirstResponder {
    BOOL accepted = [super becomeFirstResponder];
    if (accepted) {
        [_header emit:@"search_focus" value:@""];
        _header->_searchBox.needsDisplay = YES;
    }
    return accepted;
}
// The Qt menu cannot see AppKit's field editor; handle the standard editing
// key equivalents here before the menu bar receives them.
- (BOOL)performKeyEquivalent:(NSEvent *)event {
    NSText *editor = self.currentEditor;
    NSEventModifierFlags flags = event.modifierFlags & NSEventModifierFlagDeviceIndependentFlagsMask;
    if (editor && (flags == NSEventModifierFlagCommand || flags == (NSEventModifierFlagCommand | NSEventModifierFlagShift))) {
        NSString *key = event.charactersIgnoringModifiers.lowercaseString;
        BOOL shift = (flags & NSEventModifierFlagShift) != 0;
        SEL action = NULL;
        if (!shift && [key isEqual:@"x"]) action = @selector(cut:);
        else if (!shift && [key isEqual:@"c"]) action = @selector(copy:);
        else if (!shift && [key isEqual:@"v"]) action = @selector(paste:);
        else if (!shift && [key isEqual:@"a"]) action = @selector(selectAll:);
        if (action) { [editor performSelector:action withObject:self]; return YES; }
        if ([key isEqual:@"z"]) {
            NSUndoManager *undo = editor.undoManager;
            if (shift) [undo redo]; else [undo undo];
            return YES;
        }
    }
    return [super performKeyEquivalent:event];
}
@end

@interface VFTBSearchBox : NSView {
@public
    VFTBHeader *_header;
}
@end
@implementation VFTBSearchBox
- (BOOL)isFlipped { return YES; }
- (BOOL)mouseDownCanMoveWindow { return NO; }
- (void)mouseDown:(NSEvent *)event {
    (void)event;
    if (![_header dimmed]) [self.window makeFirstResponder:_header->_searchField];
}
- (void)drawRect:(NSRect)dirty {
    (void)dirty;
    BOOL focused = _header->_searchField.currentEditor != nil;
    VFTBDrawMaterial([_header material:focused ? @"field-focus" : @"field-normal"], self.bounds, self.isFlipped);
    [_header applyDim:self.bounds];
}
@end

#pragma mark - Backdrop

// In fullscreen AppKit hosts the toolbar in its own window with a neutral
// material. Paint the same header surface color the windowed header shows.
@interface VFTBBackdrop : NSView {
@public
    VFTBHeader *_header;
}
@end
@implementation VFTBBackdrop
- (NSView *)hitTest:(NSPoint)point { (void)point; return nil; }
- (void)drawRect:(NSRect)dirty {
    [[_header color:@"surface"] setFill];
    NSRectFill(dirty);
    [_header applyDim:dirty];
}
@end

// Covers the toolbar (not the window buttons) while a modal popup is open:
// every press there is a press on the dimmed background, nothing else.
@interface VFTBCatcher : NSView {
@public
    VFTBHeader *_header;
}
@end
@implementation VFTBCatcher
- (BOOL)mouseDownCanMoveWindow { return NO; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { (void)event; return YES; }
- (void)mouseDown:(NSEvent *)event { (void)event; [_header outsidePress]; }
- (void)rightMouseDown:(NSEvent *)event { (void)event; [_header outsidePress]; }
- (void)mouseUp:(NSEvent *)event { (void)event; }
- (BOOL)isAccessibilityElement { return NO; }
@end

#pragma mark - Header

@implementation VFTBHeader

- (instancetype)initWithWindow:(NSWindow *)window assets:(NSString *)assets {
    self = [super init];
    if (!self) return nil;
    _pipe[0] = _pipe[1] = -1;
    if (pipe(_pipe) != 0) { [self release]; return nil; }
    for (int i = 0; i < 2; i++) {
        fcntl(_pipe[i], F_SETFL, fcntl(_pipe[i], F_GETFL) | O_NONBLOCK);
        fcntl(_pipe[i], F_SETFD, FD_CLOEXEC);
    }
    _window = [window retain];
    _assets = [assets copy];
    _colors = [NSMutableDictionary new];
    _materials = [NSMutableDictionary new];
    _icons = [NSMutableDictionary new];
    _events = [NSMutableArray new];
    _buttons = [NSMutableDictionary new];
    _selection = [@"Forge" copy];
    _compact = NSWidth(window.frame) < 960;

    VFTBBrand *brand = [[VFTBBrand alloc] initWithFrame:NSMakeRect(0, 0, 147, 44)];
    brand->_header = self;
    _brand = brand;

    VFTBSearchBox *box = [[VFTBSearchBox alloc] initWithFrame:NSMakeRect(0, 0, 285, 40)];
    box->_header = self;
    VFTBSearchField *field = [[VFTBSearchField alloc] initWithFrame:NSMakeRect(15, 10, 258, 20)];
    field->_header = self;
    field.bezeled = NO;
    field.bordered = NO;
    field.drawsBackground = NO;
    field.focusRingType = NSFocusRingTypeNone;
    field.font = VFTBFont(15, NO);
    field.usesSingleLineMode = YES;
    field.lineBreakMode = NSLineBreakByTruncatingTail;
    field.cell.scrollable = YES;
    field.delegate = self;
    field.translatesAutoresizingMaskIntoConstraints = NO;
    [box addSubview:field];
    [NSLayoutConstraint activateConstraints:@[
        [field.leadingAnchor constraintEqualToAnchor:box.leadingAnchor constant:15],
        [field.trailingAnchor constraintEqualToAnchor:box.trailingAnchor constant:-12],
        [field.centerYAnchor constraintEqualToAnchor:box.centerYAnchor],
    ]];
    box.translatesAutoresizingMaskIntoConstraints = NO;
    NSLayoutConstraint *preferred = [box.widthAnchor constraintEqualToConstant:285];
    preferred.priority = NSLayoutPriorityDefaultLow;
    [NSLayoutConstraint activateConstraints:@[
        [box.widthAnchor constraintGreaterThanOrEqualToConstant:124],
        [box.widthAnchor constraintLessThanOrEqualToConstant:285],
        preferred,
        [box.heightAnchor constraintEqualToConstant:40],
    ]];
    _searchBox = box;
    _searchField = field;

    for (NSString *name in VFTBNavNames()) {
        VFTBButton *button = [[VFTBButton alloc] initWithFrame:NSMakeRect(0, 0, 86, 44)];
        button->_header = self;
        button->_identifier = [[VFTBNavPrefix stringByAppendingString:name] copy];
        button->_label = [name copy];
        button->_icon = [(@{@"Forge": @"download", @"Library": @"folder", @"Watch": @"play",
                            @"Activity": @"activity"}[name]) copy];
        button->_selected = [name isEqual:_selection];
        button->_leading = [name isEqual:@"Forge"] ? 0 : 10;
        _buttons[button->_identifier] = button;
        [button release];
    }
    VFTBButton *x = [[VFTBButton alloc] initWithFrame:NSMakeRect(0, 0, 28, 40)];
    x->_header = self; x->_identifier = [VFTBXID copy]; x->_icon = [@"x" copy]; x->_quiet = YES;
    x->_leading = 8;
    _buttons[VFTBXID] = x; [x release];
    VFTBButton *settings = [[VFTBButton alloc] initWithFrame:NSMakeRect(0, 0, 28, 40)];
    settings->_header = self; settings->_identifier = [VFTBSettingsID copy];
    settings->_icon = [@"icons/lucide/settings.png" copy]; settings->_imageIcon = YES;
    settings->_leading = 8; settings->_trailing = 4;
    _buttons[VFTBSettingsID] = settings; [settings release];

    // Toolbar item views use Auto Layout; without an explicit height AppKit
    // clamps them to 36pt and the Qt materials would render squashed.
    brand.translatesAutoresizingMaskIntoConstraints = NO;
    [brand.heightAnchor constraintEqualToConstant:44].active = YES;
    for (VFTBButton *button in _buttons.allValues) {
        button.translatesAutoresizingMaskIntoConstraints = NO;
        [button.heightAnchor constraintEqualToConstant:button->_label.length ? 44 : 40].active = YES;
    }
    _oldStyle = window.toolbarStyle;
    _oldSeparator = window.titlebarSeparatorStyle;
    _toolbar = [[NSToolbar alloc] initWithIdentifier:@"org.vodforge.header"];
    _toolbar.delegate = self;
    _toolbar.displayMode = NSToolbarDisplayModeIconOnly;
    _toolbar.allowsUserCustomization = NO;
    _toolbar.autosavesConfiguration = NO;
    window.toolbar = _toolbar;
    window.toolbarStyle = NSWindowToolbarStyleUnified;
    window.titlebarSeparatorStyle = NSTitlebarSeparatorStyleNone;
    [self setSearchVisible:NO];

    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    for (NSNotificationName name in @[NSWindowDidResizeNotification, NSWindowDidEnterFullScreenNotification,
                                       NSWindowDidExitFullScreenNotification, NSWindowWillEnterFullScreenNotification,
                                       NSWindowWillExitFullScreenNotification,
                                       NSWindowDidChangeBackingPropertiesNotification]) {
        [center addObserver:self selector:@selector(windowChanged:) name:name object:window];
    }
    return self;
}

- (void)dealloc {
    [_window release]; [_toolbar release]; [_assets release]; [_colors release]; [_materials release];
    [_icons release]; [_events release]; [_buttons release]; [_brand release]; [_searchBox release];
    [_searchField release]; [_searchItem release]; [_backdrop release]; [_selection release];
    [_catcher release]; [_dim release];
    for (int i = 0; i < 2; i++) if (_pipe[i] >= 0) close(_pipe[i]);
    [super dealloc];
}

- (void)close {
    if (_closed) return;
    _closed = YES;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    _searchField.delegate = nil;
    if (_window.toolbar == _toolbar) {
        if (_searchField.currentEditor) [_window makeFirstResponder:nil];
        _window.toolbar = nil;
        _window.toolbarStyle = _oldStyle;
        _window.titlebarSeparatorStyle = _oldSeparator;
    }
    _toolbar.delegate = nil;
    [_backdrop removeFromSuperview];
    [_catcher removeFromSuperview];
}

#pragma mark Events

- (void)emit:(NSString *)kind value:(NSString *)value {
    if (_closed) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"kind": kind, @"value": value ?: @""} options:0 error:NULL];
    if (!json) return;
    NSString *text = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    [_events addObject:text];
    [text release];
    if (_pipe[1] >= 0) {
        char byte = 1;
        ssize_t ignored = write(_pipe[1], &byte, 1);  // Full pipe still holds the queued event.
        (void)ignored;
    }
}

- (void)activate:(NSString *)identifier {
    if ([identifier hasPrefix:VFTBNavPrefix])
        [self emit:@"nav" value:[identifier substringFromIndex:VFTBNavPrefix.length]];
    else if ([identifier isEqual:VFTBXID])
        [self emit:@"x" value:@""];
    else if ([identifier isEqual:VFTBSettingsID])
        [self emit:@"settings" value:@""];
}

- (BOOL)dimmed { return _dim.count > 0; }
- (void)applyDim:(NSRect)rect { if (_dim.count) VFTBDimDrawn(_dim, rect); }
- (void)outsidePress { [self emit:@"outside_press" value:@""]; }

- (NSView *)toolbarView {
    NSView *view = _brand;
    while (view && ![NSStringFromClass(view.class) isEqual:@"NSToolbarView"]) view = view.superview;
    return view;
}

- (void)installCatcher {
    NSView *toolbarView = [self toolbarView];
    if (!_dim.count || !toolbarView.superview) { [_catcher removeFromSuperview]; return; }
    if (!_catcher) {
        VFTBCatcher *catcher = [[VFTBCatcher alloc] initWithFrame:NSZeroRect];
        catcher->_header = self;
        _catcher = catcher;
    }
    NSView *parent = toolbarView.superview;
    if (_catcher.superview != parent) {
        [_catcher removeFromSuperview];
        _catcher.frame = parent.bounds;
        _catcher.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
        // Above the toolbar items, below AppKit's window buttons.
        [parent addSubview:_catcher positioned:NSWindowAbove relativeTo:toolbarView];
    }
}

- (void)setDim:(NSArray *)layers {
    if ([layers isEqualToArray:_dim ?: @[]]) return;
    [_dim release];
    _dim = [layers copy];
    if (_dim.count) {
        for (VFTBButton *button in _buttons.allValues) { button->_pressed = NO; [button setHovered:NO]; }
        if (_searchField.currentEditor) [_window makeFirstResponder:_window.contentView];
    }
    [self installCatcher];
    [self redraw];
}

- (void)hover:(NSString *)identifier inside:(BOOL)inside {
    if ([identifier isEqual:VFTBXID]) [self emit:@"x_hover" value:inside ? @"1" : @"0"];
}

- (void)windowChanged:(NSNotification *)note {
    if ([note.name isEqual:NSWindowWillEnterFullScreenNotification]) _transition = 1;
    else if ([note.name isEqual:NSWindowWillExitFullScreenNotification]) _transition = 2;
    else if ([note.name isEqual:NSWindowDidEnterFullScreenNotification] ||
             [note.name isEqual:NSWindowDidExitFullScreenNotification]) _transition = 0;
    BOOL compact = NSWidth(_window.frame) < 960;
    if (compact != _compact) {
        _compact = compact;
        [_brand invalidateIntrinsicContentSize];
        _brand.needsDisplay = YES;
    }
    if ([note.name isEqual:NSWindowDidEnterFullScreenNotification] ||
        [note.name isEqual:NSWindowWillEnterFullScreenNotification])
        [self installBackdrop];
    // Coalesce resize storms into one layout event per run-loop turn.
    if (_layoutQueued) return;
    _layoutQueued = YES;
    [self performSelector:@selector(flushLayout) withObject:nil afterDelay:0];
}

- (void)flushLayout {
    _layoutQueued = NO;
    [self emit:@"layout" value:@""];
}

#pragma mark Appearance

- (NSColor *)color:(NSString *)role {
    return _colors[role] ?: [NSColor colorWithWhite:0.9 alpha:1];
}
- (NSImage *)material:(NSString *)name { return _materials[name]; }
- (NSImage *)icon:(NSString *)file {
    NSImage *image = _icons[file];
    if (!image && _assets.length) {
        image = [[[NSImage alloc] initWithContentsOfFile:[_assets stringByAppendingPathComponent:file]] autorelease];
        if (image) _icons[file] = image;
    }
    return image;
}

- (void)redraw {
    _brand.needsDisplay = YES;
    _searchBox.needsDisplay = YES;
    _backdrop.needsDisplay = YES;
    for (VFTBButton *button in _buttons.allValues) {
        [button invalidateIntrinsicContentSize];
        button.needsDisplay = YES;
    }
    NSColor *text = [self color:@"text"], *muted = [self color:@"muted"];
    _searchField.textColor = text;
    if (_searchField.placeholderString) [self setPlaceholder:_searchField.placeholderString muted:muted];
}

- (void)setPlaceholder:(NSString *)text muted:(NSColor *)muted {
    _searchField.placeholderAttributedString = [[[NSAttributedString alloc] initWithString:text
        attributes:@{NSFontAttributeName: VFTBFont(15, NO), NSForegroundColorAttributeName: muted}] autorelease];
    _searchField.placeholderString = text;
}

- (void)installBackdrop {
    NSWindow *host = _brand.window;
    if (_closed || !host) return;
    if (host == _window) {
        // Windowed: the transparent titlebar shows Qt's own header surface.
        [_backdrop removeFromSuperview];
        return;
    }
    NSView *root = host.contentView;
    if (!root) return;
    if (!_backdrop) {
        VFTBBackdrop *backdrop = [[VFTBBackdrop alloc] initWithFrame:root.bounds];
        backdrop->_header = self;
        backdrop.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
        _backdrop = backdrop;
    }
    // AppKit's fullscreen title bar blurs whatever lies behind it. Paint the
    // header surface directly beneath the toolbar view, above that blur.
    NSView *toolbarView = _brand;
    while (toolbarView && ![NSStringFromClass(toolbarView.class) isEqual:@"NSToolbarView"])
        toolbarView = toolbarView.superview;
    NSView *parent = toolbarView.superview ?: root;
    if (_backdrop.superview != parent) {
        [_backdrop removeFromSuperview];
        _backdrop.frame = parent.bounds;
        _backdrop.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
        if (toolbarView.superview) [parent addSubview:_backdrop positioned:NSWindowBelow relativeTo:toolbarView];
        else [parent addSubview:_backdrop positioned:NSWindowBelow relativeTo:nil];
    }
    _backdrop.needsDisplay = YES;
}

#pragma mark State from Qt

- (void)setSelection:(NSString *)name {
    if ([name isEqual:_selection]) return;
    [_selection release];
    _selection = [name copy];
    for (NSString *nav in VFTBNavNames()) {
        VFTBButton *button = _buttons[[VFTBNavPrefix stringByAppendingString:nav]];
        BOOL selected = [nav isEqual:name];
        if (button->_selected != selected) { button->_selected = selected; button.needsDisplay = YES; }
    }
}

- (void)setSearchVisible:(BOOL)visible {
    _searchVisible = visible;
    if (!visible && _searchField.currentEditor) [_window makeFirstResponder:_window.contentView];
    if (_searchItem) _searchItem.hidden = !visible;
}

#pragma mark Toolbar delegate

- (NSArray *)itemIdentifiers {
    NSMutableArray *ids = [NSMutableArray arrayWithObject:VFTBBrandID];
    for (NSString *name in VFTBNavNames()) [ids addObject:[VFTBNavPrefix stringByAppendingString:name]];
    [ids addObjectsFromArray:@[NSToolbarFlexibleSpaceItemIdentifier, VFTBSearchID, VFTBXID, VFTBSettingsID]];
    return ids;
}
- (NSArray *)toolbarDefaultItemIdentifiers:(NSToolbar *)toolbar { (void)toolbar; return [self itemIdentifiers]; }
- (NSArray *)toolbarAllowedItemIdentifiers:(NSToolbar *)toolbar { (void)toolbar; return [self itemIdentifiers]; }
- (NSToolbarItem *)toolbar:(NSToolbar *)toolbar itemForItemIdentifier:(NSToolbarItemIdentifier)identifier
    willBeInsertedIntoToolbar:(BOOL)inserted {
    (void)toolbar; (void)inserted;
    NSToolbarItem *item = [[[NSToolbarItem alloc] initWithItemIdentifier:identifier] autorelease];
    item.bordered = NO;
    if ([identifier isEqual:VFTBBrandID]) {
        item.view = _brand;
        item.label = @"VODForge";
        item.visibilityPriority = NSToolbarItemVisibilityPriorityUser;
    } else if ([identifier isEqual:VFTBSearchID]) {
        item.view = _searchBox;
        item.label = @"Search";
        item.visibilityPriority = NSToolbarItemVisibilityPriorityLow;
        item.hidden = !_searchVisible;
        [_searchItem release];
        _searchItem = [item retain];
    } else {
        VFTBButton *button = _buttons[identifier];
        if (!button) return nil;
        item.view = button;
        item.label = button.accessibilityLabel;
        item.visibilityPriority = NSToolbarItemVisibilityPriorityHigh;
    }
    return item;
}

#pragma mark Search delegate

- (void)controlTextDidChange:(NSNotification *)note {
    (void)note;
    [self emit:@"search" value:_searchField.stringValue];
}
- (void)controlTextDidEndEditing:(NSNotification *)note {
    (void)note;
    _searchBox.needsDisplay = YES;
    [self emit:@"search_blur" value:@""];
}
- (BOOL)control:(NSControl *)control textView:(NSTextView *)view doCommandBySelector:(SEL)command {
    (void)control; (void)view;
    if (command == @selector(cancelOperation:)) {
        [_window makeFirstResponder:_window.contentView];
        return YES;
    }
    return NO;
}

#pragma mark Geometry

static NSRect VFTBContentRect(NSWindow *main, NSView *view) {
    if (!view.window || !main.contentView) return NSZeroRect;
    NSRect screen = [view.window convertRectToScreen:[view convertRect:view.bounds toView:nil]];
    NSRect local = [main.contentView convertRect:[main convertRectFromScreen:screen] fromView:nil];
    if (!main.contentView.isFlipped) local.origin.y = NSHeight(main.contentView.bounds) - NSMaxY(local);
    return local;
}

- (NSRect)anchor:(NSString *)name {
    NSView *view = [name isEqual:@"settings"] ? _buttons[VFTBSettingsID]
        : [name isEqual:@"x"] ? _buttons[VFTBXID]
        : [name isEqual:@"search"] ? _searchBox : _brand;
    return VFTBContentRect(_window, view);
}

// Where AppKit's window chrome is right now. In fullscreen the toolbar lives in
// its own window that the menu bar pushes down; `revealed` is how far below its
// hidden position the toolbar currently sits (0 when the menu bar is hidden).
// Modal panels opened while this moves stall AppKit's animation mid-way.
- (void)chrome:(double *)out {
    BOOL fullscreen = (_window.styleMask & NSWindowStyleMaskFullScreen) != 0;
    double revealed = 0, x = 0;
    NSWindow *host = _brand.window;
    NSView *viewer = _brand.superview;
    if (host && viewer) {
        NSRect r = [host convertRectToScreen:[_brand convertRect:_brand.bounds toView:nil]];
        NSScreen *screen = host.screen ?: _window.screen;
        x = NSMinX(r);
        if (fullscreen && host != _window && screen) {
            double hiddenOffset = (NSHeight(viewer.bounds) - NSHeight(_brand.bounds)) / 2;
            revealed = MAX(0, NSMaxY(screen.frame) - NSMaxY(r) - hiddenOffset);
        }
    }
    out[0] = fullscreen; out[1] = _transition; out[2] = revealed; out[3] = x;
}

- (double)toolbarHeight {
    NSRect layout = _window.contentLayoutRect;
    return MAX(0, NSHeight(_window.frame) - NSMaxY(layout));
}
@end

#pragma mark - C interface (main thread only)

#define VFTB_GUARD(h) if (!NSThread.isMainThread || !(h) || ((VFTBHeader *)(h))->_closed) return 0

unsigned vf_toolbar_abi_version(void) { return 1; }

void *vf_toolbar_create(void *window, const char *assets) {
    if (!NSThread.isMainThread || !window) return NULL;
    NSWindow *target = (NSWindow *)window;
    if (![target isKindOfClass:NSWindow.class] || target.toolbar) return NULL;
    NSString *path = assets ? [NSString stringWithUTF8String:assets] : @"";
    return [[VFTBHeader alloc] initWithWindow:target assets:path ?: @""];
}

int vf_toolbar_event_fd(void *handle) {
    if (!handle) return -1;
    return ((VFTBHeader *)handle)->_pipe[0];
}

// Copies the oldest queued event into buffer. Returns its byte length, 0 when
// the queue is empty, or -1 when the buffer is too small (event is retained).
int vf_toolbar_next_event(void *handle, char *buffer, size_t capacity) {
    if (!NSThread.isMainThread || !handle || !buffer) return -1;
    VFTBHeader *header = handle;
    char drain[64];
    while (header->_pipe[0] >= 0 && read(header->_pipe[0], drain, sizeof drain) > 0) {}
    if (!header->_events.count) return 0;
    const char *text = [header->_events[0] UTF8String];
    size_t length = strlen(text);
    if (length + 1 > capacity) return -1;
    memcpy(buffer, text, length + 1);
    [header->_events removeObjectAtIndex:0];
    return (int)length;
}

int vf_toolbar_set_color(void *handle, const char *role, double r, double g, double b, double a) {
    VFTB_GUARD(handle);
    if (!role) return 0;
    VFTBHeader *header = handle;
    header->_colors[[NSString stringWithUTF8String:role]] =
        [NSColor colorWithSRGBRed:r green:g blue:b alpha:a];
    return 1;
}

// PNG at 2x of (width x height) points, drawn nine-part with equal caps.
int vf_toolbar_set_material(void *handle, const char *name, const void *png, size_t length,
                            double width, double height, double cap) {
    VFTB_GUARD(handle);
    if (!name || !png || !length || width <= 0 || height <= 0 || cap < 0) return 0;
    NSData *data = [NSData dataWithBytes:png length:length];
    NSImage *image = [[[NSImage alloc] initWithData:data] autorelease];
    if (!image) return 0;
    image.size = NSMakeSize(width, height);
    image.capInsets = NSEdgeInsetsMake(cap, cap, cap, cap);
    image.resizingMode = NSImageResizingModeStretch;
    ((VFTBHeader *)handle)->_materials[[NSString stringWithUTF8String:name]] = image;
    return 1;
}

int vf_toolbar_redraw(void *handle) {
    VFTB_GUARD(handle);
    [(VFTBHeader *)handle redraw];
    return 1;
}

int vf_toolbar_set_selection(void *handle, const char *name) {
    VFTB_GUARD(handle);
    if (!name) return 0;
    [(VFTBHeader *)handle setSelection:[NSString stringWithUTF8String:name]];
    return 1;
}

int vf_toolbar_set_search(void *handle, int visible, const char *placeholder, const char *text,
                          const char *accessible) {
    VFTB_GUARD(handle);
    VFTBHeader *header = handle;
    if (placeholder) [header setPlaceholder:[NSString stringWithUTF8String:placeholder] muted:[header color:@"muted"]];
    if (accessible) header->_searchField.accessibilityLabel = [NSString stringWithUTF8String:accessible];
    if (text) {
        NSString *value = [NSString stringWithUTF8String:text];
        // Never rewrite the field under the user's caret with its own echo.
        if (value && ![value isEqual:header->_searchField.stringValue]) header->_searchField.stringValue = value;
    }
    [header setSearchVisible:visible != 0];
    return 1;
}

// Modal Qt surfaces block header input; AppKit's field must follow them.
int vf_toolbar_set_interactive(void *handle, int interactive) {
    VFTB_GUARD(handle);
    VFTBHeader *header = handle;
    if (!interactive && header->_searchField.currentEditor) [header->_window makeFirstResponder:header->_window.contentView];
    header->_searchField.enabled = interactive != 0;
    return 1;
}

int vf_toolbar_search_focused(void *handle) {
    VFTB_GUARD(handle);
    return ((VFTBHeader *)handle)->_searchField.currentEditor != nil;
}

// Edit menu commands chosen with the pointer reach Qt, not the field editor.
int vf_toolbar_edit(void *handle, const char *method) {
    VFTB_GUARD(handle);
    VFTBHeader *header = handle;
    NSText *editor = header->_searchField.currentEditor;
    if (!editor || !method) return 0;
    NSString *name = [NSString stringWithUTF8String:method];
    if ([name isEqual:@"undo"]) { [editor.undoManager undo]; return 1; }
    if ([name isEqual:@"redo"]) { [editor.undoManager redo]; return 1; }
    NSDictionary *actions = @{@"cut": @"cut:", @"copy": @"copy:", @"paste": @"paste:", @"selectAll": @"selectAll:"};
    NSString *selector = actions[name];
    if (!selector) return 0;
    [editor performSelector:NSSelectorFromString(selector) withObject:header->_searchField];
    return 1;
}

// rgba holds count layers of 4 components (sRGB, straight alpha), bottom first.
int vf_toolbar_set_dim(void *handle, int count, const double *rgba) {
    VFTB_GUARD(handle);
    if (count < 0 || count > 16 || (count && !rgba)) return 0;
    NSMutableArray *layers = [NSMutableArray array];
    for (int i = 0; i < count; i++) {
        const double *c = rgba + 4 * i;
        if (c[3] <= 0.001) continue;
        [layers addObject:[NSColor colorWithSRGBRed:c[0] green:c[1] blue:c[2] alpha:MIN(1, c[3])]];
    }
    [(VFTBHeader *)handle setDim:layers];
    return 1;
}

int vf_toolbar_chrome(void *handle, double *out) {
    VFTB_GUARD(handle);
    if (!out) return 0;
    [(VFTBHeader *)handle chrome:out];
    return 1;
}

int vf_toolbar_anchor(void *handle, const char *name, double *out) {
    VFTB_GUARD(handle);
    if (!name || !out) return 0;
    NSRect r = [(VFTBHeader *)handle anchor:[NSString stringWithUTF8String:name]];
    if (NSIsEmptyRect(r)) return 0;
    out[0] = NSMinX(r); out[1] = NSMinY(r); out[2] = NSWidth(r); out[3] = NSHeight(r);
    return 1;
}

double vf_toolbar_height(void *handle) {
    if (!NSThread.isMainThread || !handle || ((VFTBHeader *)handle)->_closed) return -1;
    return [(VFTBHeader *)handle toolbarHeight];
}

int vf_toolbar_destroy(void *handle) {
    if (!NSThread.isMainThread || !handle) return 0;
    VFTBHeader *header = handle;
    [NSObject cancelPreviousPerformRequestsWithTarget:header];
    [header close];
    [header release];
    return 1;
}

// Test probe: draws a material through the same flipped-view path the header
// uses and returns top-down RGBA rows, so orientation is verified by pixels.
int vf_toolbar_probe_material(const void *png, size_t length, double width, double height, double cap,
                              int pixels_wide, int pixels_high, unsigned char *rgba) {
    if (!png || !length || !rgba || pixels_wide <= 0 || pixels_high <= 0 || width <= 0 || height <= 0) return 0;
    @autoreleasepool {
        NSImage *image = [[[NSImage alloc] initWithData:[NSData dataWithBytes:png length:length]] autorelease];
        if (!image) return 0;
        image.size = NSMakeSize(width, height);
        image.capInsets = NSEdgeInsetsMake(cap, cap, cap, cap);
        image.resizingMode = NSImageResizingModeStretch;
        CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CGContextRef context = CGBitmapContextCreate(rgba, pixels_wide, pixels_high, 8, pixels_wide * 4, space,
                                                     (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
        CGColorSpaceRelease(space);
        if (!context) return 0;
        CGContextClearRect(context, CGRectMake(0, 0, pixels_wide, pixels_high));
        // Match a flipped NSView: origin top-left, y grows downward, in points.
        CGContextTranslateCTM(context, 0, pixels_high);
        CGContextScaleCTM(context, pixels_wide / width, -pixels_high / height);
        NSGraphicsContext *graphics = [NSGraphicsContext graphicsContextWithCGContext:context flipped:YES];
        [NSGraphicsContext saveGraphicsState];
        NSGraphicsContext.currentContext = graphics;
        VFTBDrawMaterial(image, NSMakeRect(0, 0, width, height), YES);
        [NSGraphicsContext restoreGraphicsState];
        CGContextFlush(context);
        CGContextRelease(context);
    }
    return 1;
}
