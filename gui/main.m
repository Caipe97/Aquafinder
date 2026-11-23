/* Aquafinder.app: a small Panther (10.3) Cocoa front end for aquafinder.sh
 * (it runs on Tiger too).
 *
 * It never touches system files itself. It runs the bundled
 *   sh aquafinder.sh status                     (as the user, to show state)
 *   sh aquafinder.sh install|restore <part>     (as root, after one password)
 * so every check the script makes (recognised file, backup, verification)
 * still applies. Built on Panther with gcc 3.3: no properties, blocks or
 * fast enumeration, and the window is laid out in code (no nib).
 */
#import <Cocoa/Cocoa.h>
#import <Security/Security.h>
#import <ApplicationServices/ApplicationServices.h>   /* Apple Events; Carbon.h needs CarbonSound headers Panther may lack */
#include <sys/wait.h>

enum { ST_UNKNOWN, ST_ORIGINAL, ST_INSTALLED, ST_OLD, ST_MIXED };

/* One row per script component. A component can cover several files, and
 * "status" prints one line per file: every line whose prefix is listed
 * counts towards the row's state. */
typedef struct {
    const char *part;          /* argument to install/restore */
    const char *prefixes;      /* space-separated status line prefixes */
    const char *title, *desc;
    BOOL restart;              /* needs a restart to show everywhere */
    int parent;                /* option of PARTS[parent], or -1 */
    /* Preview pictures (Resources/<name>.png, made by tools/previews.py):
     * without the part, with it, and with it plus its ticked option. */
    const char *before, *after, *afterOption;
} Part;

/* An option row comes right after its parent, so Apply runs the parent's
 * install/restore first. */
static const Part PARTS[] = {
    { "finder", "finder grip", "Aqua Finder windows",
      "Swaps the brushed metal for plain Aqua, with the item count up top like in Jaguar.", NO, -1,
      "finder-metal", "finder-aqua", "finder-stripes" },
    { "sidebar", "stripes header well", "Sidebar:",
      "Plain, pinstriped, under a list header like the file list's, or as an inset list on pinstripes.", NO, 0,
      "sidebar-plain", "sidebar-plain", NULL },
    { "titlebars", "titlebars appkit", "Jaguar title bars",
      "Jaguar's pinstriped title bars in every app, see-through in the background. Takes a restart.", YES, -1,
      "titlebar-panther", "titlebar-jaguar", NULL },
    { "logo", "logo", "Jaguar logo and Finder icon",
      "The classic Garamond \"Mac OS X\" at login and in About This Mac, plus Jaguar's Finder icon.", NO, -1,
      "logo-panther", "logo-jaguar", NULL },
};
#define NPARTS ((int)(sizeof PARTS / sizeof PARTS[0]))
#define S(c) [NSString stringWithCString:(c)]

/* The "sidebar" row is a pop-up of the Finder's sidebar styles, not a
 * checkbox: the script's style parts (none: the plain sidebar), and their
 * names and preview pictures. The script prints a status line per style
 * part; the one "installed" is the Finder's style. */
#define SIDEBAR_ROW 1
#define NSTYLES 4
static const char *STYLE_PART[NSTYLES] = { NULL, "stripes", "header", "well" };
static const char *STYLE_TITLE[NSTYLES] = { "Plain", "Pinstriped", "List header", "Inset" };
static const char *STYLE_NAME[NSTYLES] = { "plain", "pinstriped", "list header", "inset" };
static const char *STYLE_FINDER[NSTYLES] = { "finder-aqua", "finder-stripes", "finder-header", "finder-well" };
static const char *STYLE_SIDEBAR[NSTYLES] = { "sidebar-plain", "sidebar-stripes", "sidebar-header", "sidebar-well" };

static int parseState(NSString *line)
{
    if ([line rangeOfString:@"older Aquafinder installed"].location != NSNotFound) return ST_OLD;
    if ([line rangeOfString:@"Aquafinder installed"].location != NSNotFound) return ST_INSTALLED;
    if ([line rangeOfString:@": original"].location != NSNotFound) return ST_ORIGINAL;
    return ST_UNKNOWN;
}

/* Fold the states of a part's files: all alike -> that; any unrecognised ->
 * unknown (the script would skip it); any older -> old; else mixed. */
static int combine(int acc, int st, BOOL first)
{
    if (first) return st;
    if (acc == ST_UNKNOWN || st == ST_UNKNOWN) return ST_UNKNOWN;
    if (acc == st) return acc;
    if (acc == ST_OLD || st == ST_OLD) return ST_OLD;
    return ST_MIXED;
}

#define GITHUB "https://github.com/Caipe97/Aquafinder"

/* One option's row. A click anywhere but the checkbox picks the row for the
 * preview; it's drawn highlighted while picked. */
@interface RowView : NSView
{
    id target;
    int index;
    BOOL picked;
    NSView *check;
}
- (void)setTarget:(id)t index:(int)i check:(NSView *)c;
- (int)index;
- (void)setPicked:(BOOL)p;
@end

@implementation RowView
- (void)setTarget:(id)t index:(int)i check:(NSView *)c { target = t; index = i; check = c; }
- (int)index { return index; }
- (void)setPicked:(BOOL)p { if (p != picked) { picked = p; [self setNeedsDisplay:YES]; } }
- (BOOL)acceptsFirstMouse:(NSEvent *)e { return YES; }

- (NSView *)hitTest:(NSPoint)p
{
    NSView *v = [super hitTest:p];
    if (v == nil || v == check || [v isDescendantOf:check]) return v;
    return self;   /* the labels don't take clicks */
}

- (void)mouseDown:(NSEvent *)e
{
    [target performSelector:@selector(pickRow:) withObject:self];
}

- (void)drawRect:(NSRect)r
{
    NSRect b = NSInsetRect([self bounds], 1.5, 1.5);
    float rad = 6;
    NSBezierPath *p;
    if (!picked) return;
    /* a rounded rectangle (bezierPathWithRoundedRect is 10.5+) */
    p = [NSBezierPath bezierPath];
    [p moveToPoint:NSMakePoint(NSMidX(b), NSMaxY(b))];
    [p appendBezierPathWithArcFromPoint:NSMakePoint(NSMaxX(b), NSMaxY(b)) toPoint:NSMakePoint(NSMaxX(b), NSMidY(b)) radius:rad];
    [p appendBezierPathWithArcFromPoint:NSMakePoint(NSMaxX(b), NSMinY(b)) toPoint:NSMakePoint(NSMidX(b), NSMinY(b)) radius:rad];
    [p appendBezierPathWithArcFromPoint:NSMakePoint(NSMinX(b), NSMinY(b)) toPoint:NSMakePoint(NSMinX(b), NSMidY(b)) radius:rad];
    [p appendBezierPathWithArcFromPoint:NSMakePoint(NSMinX(b), NSMaxY(b)) toPoint:NSMakePoint(NSMidX(b), NSMaxY(b)) radius:rad];
    [p closePath];
    [[NSColor colorWithCalibratedRed:0.22 green:0.46 blue:0.86 alpha:0.10] set];
    [p fill];
    [[NSColor colorWithCalibratedRed:0.22 green:0.46 blue:0.86 alpha:0.45] set];
    [p setLineWidth:1];
    [p stroke];
}
@end

@interface Controller : NSObject
{
    NSWindow *window;
    NSButton *box[NPARTS], *applyButton;
    NSTextField *status[NPARTS], *footer, *beforeLabel, *afterLabel;
    RowView *row[NPARTS];
    NSImageView *beforeView, *afterView;
    NSMutableDictionary *images;
    NSProgressIndicator *spinner;
    NSPopUpButton *stylePopup;
    int state[NPARTS], picked, styleNow;
    AuthorizationRef auth;
}
- (void)changed:(id)sender;
- (void)showPreview;
- (void)pickRow:(RowView *)r;
- (void)openGitHub:(id)sender;
- (NSTextView *)textViewIn:(NSView *)v;
@end

@implementation Controller

- (NSString *)script
{
    return [[NSBundle mainBundle] pathForResource:@"aquafinder" ofType:@"sh"];
}

- (NSTextField *)label:(NSString *)s frame:(NSRect)r gray:(BOOL)gray in:(NSView *)v
{
    NSTextField *t = [[[NSTextField alloc] initWithFrame:r] autorelease];
    [t setStringValue:s];
    [t setEditable:NO]; [t setSelectable:NO]; [t setBezeled:NO]; [t setDrawsBackground:NO];
    [t setFont:[NSFont systemFontOfSize:11]];
    if (gray) [t setTextColor:[NSColor disabledControlTextColor]];
    [v addSubview:t];
    return t;
}

- (NSTextField *)label:(NSString *)s frame:(NSRect)r gray:(BOOL)gray
{
    return [self label:s frame:r gray:gray in:[window contentView]];
}

- (NSImage *)image:(const char *)name
{
    NSImage *im;
    NSString *path;
    if (name == NULL) return nil;
    if (images == nil) images = [[NSMutableDictionary alloc] init];
    if ((im = [images objectForKey:S(name)]) != nil) return im;
    path = [[NSBundle mainBundle] pathForResource:S(name) ofType:@"png"];
    im = path ? [[[NSImage alloc] initWithContentsOfFile:path] autorelease] : nil;
    if (im) [images setObject:im forKey:S(name)];
    return im;
}

/* The window: options on the left, each in a row you can click to preview
 * it; the before/after pictures on the right; Apply along the bottom. It
 * fits an 800x600 screen. */
#define ROW_H   88      /* one option's row */
#define PV_X    446     /* preview column */
#define PV_W    286     /* a 280x170 picture in a gray bezel */
#define PV_H    176

- (void)buildWindow
{
    float h = 130 + NPARTS * ROW_H, w = PV_X + PV_W + 18, top = h - 64;
    int i;
    window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, w, h)
        styleMask:(NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask)
        backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"Aquafinder"];

    [self label:@"Give Panther and Tiger a cleaner look that fits small screens. Click an option to preview it. Applying asks for an admin password."
          frame:NSMakeRect(20, h - 52, 410, 42) gray:NO];

    for (i = 0; i < NPARTS; i++) {
        float x = PARTS[i].parent < 0 ? 8 : 28, rh = ROW_H - 6;   /* options sit under their part */
        RowView *r = [[[RowView alloc] initWithFrame:NSMakeRect(10, top - i * ROW_H - rh, 420, rh)] autorelease];
        NSButton *b;
        if (i == SIDEBAR_ROW) {   /* "Sidebar:" and the styles' pop-up */
            int k;
            NSTextField *t = [self label:S(PARTS[i].title) frame:NSMakeRect(x + 2, rh - 23, 60, 18) gray:NO in:r];
            [t setFont:[NSFont systemFontOfSize:13]];
            stylePopup = [[[NSPopUpButton alloc] initWithFrame:NSMakeRect(x + 62, rh - 28, 150, 26) pullsDown:NO] autorelease];
            for (k = 0; k < NSTYLES; k++) [stylePopup addItemWithTitle:S(STYLE_TITLE[k])];
            [stylePopup setTarget:self]; [stylePopup setAction:@selector(changed:)];
            b = stylePopup;
        } else {
            b = [[[NSButton alloc] initWithFrame:NSMakeRect(x, rh - 24, 408 - x, 20)] autorelease];
            [b setButtonType:NSSwitchButton];
            [b setTitle:S(PARTS[i].title)];
            [b setFont:PARTS[i].parent < 0 ? [NSFont boldSystemFontOfSize:13] : [NSFont systemFontOfSize:13]];
            [b setTarget:self]; [b setAction:@selector(changed:)];
        }
        [r addSubview:b];
        [r setTarget:self index:i check:b];
        [[window contentView] addSubview:r];
        box[i] = b; row[i] = r;
        {   /* the status line goes right under the description, one line or two */
            NSTextField *d = [self label:S(PARTS[i].desc) frame:NSMakeRect(x + 20, rh - 58, 390 - x, 30) gray:NO in:r];
            float dh = [[d cell] cellSizeForBounds:NSMakeRect(0, 0, 390 - x, 1000)].height;
            [d setFrame:NSMakeRect(x + 20, rh - 28 - dh, 390 - x, dh)];
            status[i] = [self label:@"" frame:NSMakeRect(x + 20, rh - 46 - dh, 390 - x, 16) gray:YES in:r];
        }
    }

    beforeLabel = [self label:@"Before" frame:NSMakeRect(PV_X + 2, h - 32, PV_W, 16) gray:NO];
    beforeView = [[[NSImageView alloc] initWithFrame:NSMakeRect(PV_X, h - 36 - PV_H, PV_W, PV_H)] autorelease];
    afterLabel = [self label:@"After" frame:NSMakeRect(PV_X + 2, h - 58 - PV_H, PV_W, 16) gray:NO];
    afterView = [[[NSImageView alloc] initWithFrame:NSMakeRect(PV_X, h - 62 - 2 * PV_H, PV_W, PV_H)] autorelease];
    [beforeLabel setFont:[NSFont boldSystemFontOfSize:11]];
    [afterLabel setFont:[NSFont boldSystemFontOfSize:11]];
    for (i = 0; i < 2; i++) {
        NSImageView *v = i ? afterView : beforeView;
        [v setImageFrameStyle:NSImageFrameGrayBezel];
        [v setImageScaling:NSScaleNone];
        [v setEditable:NO];
        [[window contentView] addSubview:v];
    }

    NSBox *line = [[[NSBox alloc] initWithFrame:NSMakeRect(20, 62, w - 40, 1)] autorelease];
    [line setBoxType:NSBoxSeparator];
    [[window contentView] addSubview:line];

    footer = [self label:@"" frame:NSMakeRect(20, 18, w - 196, 30) gray:YES];
    spinner = [[[NSProgressIndicator alloc] initWithFrame:NSMakeRect(w - 164, 24, 16, 16)] autorelease];
    [spinner setStyle:NSProgressIndicatorSpinningStyle];
    [spinner setControlSize:NSSmallControlSize];
    [spinner setDisplayedWhenStopped:NO];
    [spinner setUsesThreadedAnimation:YES];
    [[window contentView] addSubview:spinner];

    applyButton = [[[NSButton alloc] initWithFrame:NSMakeRect(w - 140, 14, 126, 32)] autorelease];
    [applyButton setBezelStyle:NSRoundedBezelStyle];
    [applyButton setTitle:@"Apply"];
    [applyButton setKeyEquivalent:@"\r"];
    [applyButton setTarget:self]; [applyButton setAction:@selector(apply:)];
    [[window contentView] addSubview:applyButton];

    [window center];
}

/* Run the script unprivileged and return its output. */
- (NSString *)runStatus
{
    NSTask *t = [[[NSTask alloc] init] autorelease];
    NSPipe *p = [NSPipe pipe];
    [t setLaunchPath:@"/bin/sh"];
    [t setArguments:[NSArray arrayWithObjects:[self script], @"status", nil]];
    [t setStandardOutput:p]; [t setStandardError:p];
    [t launch];
    NSData *d = [[p fileHandleForReading] readDataToEndOfFile];
    [t waitUntilExit];
    return [[[NSString alloc] initWithData:d encoding:NSASCIIStringEncoding] autorelease];
}

- (int)stateOf:(int)i inText:(NSString *)text
{
    NSArray *lines = [text componentsSeparatedByString:@"\n"];
    NSArray *prefixes = [S(PARTS[i].prefixes) componentsSeparatedByString:@" "];
    int acc = ST_UNKNOWN; BOOL first = YES;
    unsigned l, k;
    for (l = 0; l < [lines count]; l++) {
        NSString *line = [lines objectAtIndex:l];
        for (k = 0; k < [prefixes count]; k++)
            if ([line hasPrefix:[[prefixes objectAtIndex:k] stringByAppendingString:@":"]]) {
                acc = combine(acc, parseState(line), first); first = NO;
            }
    }
    return acc;   /* no lines at all: unknown */
}

- (NSString *)describe:(int)st
{
    switch (st) {
    case ST_ORIGINAL:  return @"Now: not installed.";
    case ST_INSTALLED: return @"Now: installed.";
    case ST_OLD:       return @"Now: an older version. Apply to update it.";
    case ST_MIXED:     return @"Now: partly installed. Apply to finish.";
    }
    return @"Not available: a system file here isn't one Aquafinder knows.";
}

/* The Finder's sidebar style: the style part whose status line says installed (0: plain). */
- (int)styleInText:(NSString *)text
{
    int k;
    for (k = 1; k < NSTYLES; k++) {
        NSString *prefix = [S(STYLE_PART[k]) stringByAppendingString:@": Aquafinder installed"];
        NSArray *lines = [text componentsSeparatedByString:@"\n"];
        unsigned l;
        for (l = 0; l < [lines count]; l++)
            if ([[lines objectAtIndex:l] hasPrefix:prefix]) return k;
    }
    return 0;
}

- (void)refresh
{
    NSString *text = [self runStatus];
    int i;
    for (i = 0; i < NPARTS; i++) {
        int st = state[i] = [self stateOf:i inText:text];
        if (i == SIDEBAR_ROW) {   /* the styles' pop-up: the installed one */
            styleNow = [self styleInText:text];
            [stylePopup selectItemAtIndex:styleNow];
            [stylePopup setEnabled:(st != ST_UNKNOWN)];
            [status[i] setStringValue:st == ST_UNKNOWN ? [self describe:st]
                : [NSString stringWithFormat:@"Now: %s.", STYLE_NAME[styleNow]]];
            continue;
        }
        [box[i] setEnabled:(st != ST_UNKNOWN)];
        [box[i] setState:(st == ST_INSTALLED || st == ST_OLD || st == ST_MIXED) ? NSOnState : NSOffState];
        [status[i] setStringValue:[self describe:st]];
        if (PARTS[i].parent >= 0 && st != ST_UNKNOWN)   /* an option: on or off, not "installed" */
            [status[i] setStringValue:st == ST_INSTALLED ? @"Now: on." : @"Now: off."];
    }
    [self changed:nil];
}

/* The argument for install/restore: the sidebar row's is the style's part. */
- (NSString *)partFor:(int)i
{
    if (i != SIDEBAR_ROW) return S(PARTS[i].part);
    if ([stylePopup indexOfSelectedItem] == 0) return S(STYLE_PART[styleNow]);   /* restore it */
    return S(STYLE_PART[[stylePopup indexOfSelectedItem]]);
}

/* What Apply would do for one part: nil, @"install" or @"restore". */
- (NSString *)verbFor:(int)i
{
    if (state[i] == ST_UNKNOWN) return nil;
    if (i == SIDEBAR_ROW) {   /* a style picked: install it; plain: restore the one installed */
        int k = [stylePopup indexOfSelectedItem];
        if (k == styleNow) return nil;
        return k ? @"install" : @"restore";
    }
    if ([box[i] state] == NSOnState) return state[i] == ST_INSTALLED ? nil : @"install";
    return state[i] == ST_ORIGINAL ? nil : @"restore";
}

- (void)changed:(id)sender
{
    BOOL any = NO;
    int i;
    /* An option needs its part: ticking it ticks the part, unticking the
     * part unticks it. A sidebar style other than plain is the option on. */
    for (i = 0; i < NPARTS; i++) {
        int p = PARTS[i].parent;
        if (p < 0) continue;
        if (i == SIDEBAR_ROW) {
            if (sender == stylePopup && [stylePopup indexOfSelectedItem] && [box[p] isEnabled]) [box[p] setState:NSOnState];
            if ([box[p] state] == NSOffState) [stylePopup selectItemAtIndex:0];
            continue;
        }
        if (sender == box[i] && [box[i] state] == NSOnState && [box[p] isEnabled]) [box[p] setState:NSOnState];
        if ([box[p] state] == NSOffState) [box[i] setState:NSOffState];
    }
    for (i = 0; i < NPARTS; i++) {
        if ([self verbFor:i]) any = YES;
        if (sender == box[i]) picked = i;   /* ticking an option previews it */
    }
    [applyButton setEnabled:any];
    if (sender != nil) [footer setStringValue:any ? @"" : @"Nothing to change."];
    [self showPreview];
}

/* Before: the picked part left out. After: what Apply leaves, so it follows
 * the ticks (and the Finder's picture picks up the sidebar style). */
- (void)showPreview
{
    const Part *p = &PARTS[picked];
    int i, k = [stylePopup indexOfSelectedItem];
    BOOL on = picked == SIDEBAR_ROW ? k != 0 : [box[picked] state] == NSOnState;
    for (i = 0; i < NPARTS; i++)
        [row[i] setPicked:(i == picked)];
    [beforeView setImage:[self image:p->before]];
    if (picked == SIDEBAR_ROW) {
        [afterView setImage:[self image:STYLE_SIDEBAR[k]]];
        [afterLabel setStringValue:on ? [NSString stringWithFormat:@"After: the %s sidebar", STYLE_NAME[k]]
                                      : @"After: the plain sidebar"];
    } else if (PARTS[SIDEBAR_ROW].parent == picked && on && k) {
        [afterView setImage:[self image:STYLE_FINDER[k]]];
        [afterLabel setStringValue:[NSString stringWithFormat:@"After, with the %s sidebar", STYLE_NAME[k]]];
    } else {
        [afterView setImage:[self image:on ? p->after : p->before]];
        [afterLabel setStringValue:on ? @"After" : @"After: the stock look (unticked)"];
    }
}

- (void)pickRow:(RowView *)r
{
    picked = [r index];
    [self showPreview];
}

- (BOOL)authorize
{
    AuthorizationItem item = { kAuthorizationRightExecute, 0, NULL, 0 };
    AuthorizationRights rights = { 1, &item };
    AuthorizationFlags fl = kAuthorizationFlagInteractionAllowed | kAuthorizationFlagExtendRights
                          | kAuthorizationFlagPreAuthorize;
    if (auth == NULL && AuthorizationCreate(NULL, kAuthorizationEmptyEnvironment,
                                            kAuthorizationFlagDefaults, &auth) != errAuthorizationSuccess)
        return NO;
    return AuthorizationCopyRights(auth, &rights, kAuthorizationEmptyEnvironment, fl, NULL)
           == errAuthorizationSuccess;
}

/* Run "sh aquafinder.sh <verb> <part>" as root; append its output to log. */
- (BOOL)run:(NSString *)verb part:(NSString *)part log:(NSMutableString *)log
{
    char *args[] = { (char *)[[self script] fileSystemRepresentation],
                     (char *)[verb UTF8String], (char *)[part UTF8String], NULL };
    FILE *pipe = NULL;
    char buf[512];
    int st = 0;
    if (AuthorizationExecuteWithPrivileges(auth, "/bin/sh", kAuthorizationFlagDefaults, args, &pipe)
        != errAuthorizationSuccess) {
        [log appendFormat:@"%@: could not start the installer.\n", part];
        return NO;
    }
    while (fgets(buf, sizeof buf, pipe)) [log appendString:[NSString stringWithCString:buf]];
    fclose(pipe);
    wait(&st);   /* reap the privileged child; its exit code is the script's */
    return WIFEXITED(st) && WEXITSTATUS(st) == 0;
}

- (void)restartMac
{
    /* Ask loginwindow to restart, as Apple's QA1134 does: it shows no extra dialog. */
    ProcessSerialNumber psn = { 0, kSystemProcess };
    AEAddressDesc target; AppleEvent ev, reply;
    if (AECreateDesc(typeProcessSerialNumber, &psn, sizeof psn, &target) != noErr) return;
    if (AECreateAppleEvent(kCoreEventClass, kAERestart, &target, kAutoGenerateReturnID,
                           kAnyTransactionID, &ev) == noErr) {
        AESendMessage(&ev, &reply, kAENoReply, kAEDefaultTimeout);   /* AESend lives in HIToolbox */
        AEDisposeDesc(&ev);
    }
    AEDisposeDesc(&target);
}

- (void)apply:(id)sender
{
    NSString *verb[NPARTS];
    NSMutableString *log = [NSMutableString string];
    BOOL ok = YES, any = NO, restart = NO;
    int i;

    for (i = 0; i < NPARTS; i++) {
        verb[i] = [self verbFor:i];
        if (verb[i]) { any = YES; if (PARTS[i].restart) restart = YES; }
    }
    /* installing a sidebar style installs the Finder too, in that style */
    if (verb[SIDEBAR_ROW] && [verb[SIDEBAR_ROW] isEqualToString:@"install"]
        && verb[PARTS[SIDEBAR_ROW].parent] && [verb[PARTS[SIDEBAR_ROW].parent] isEqualToString:@"install"])
        verb[PARTS[SIDEBAR_ROW].parent] = nil;
    if (!any) return;
    if (![self authorize]) return;   /* cancelled at the password dialog */

    [applyButton setEnabled:NO];
    for (i = 0; i < NPARTS; i++) [box[i] setEnabled:NO];   /* (the pop-up is box[SIDEBAR_ROW]) */
    [footer setStringValue:@"Working..."];
    [spinner startAnimation:nil];
    [window display];
    for (i = 0; i < NPARTS; i++)
        if (verb[i]) ok = [self run:verb[i] part:[self partFor:i] log:log] && ok;
    [spinner stopAnimation:nil];
    [footer setStringValue:@""];
    [self refresh];

    if (!ok) {
        NSRunAlertPanel(@"Some changes weren't made", @"%@", @"OK", nil, nil, log);
    } else if (restart) {
        int r = NSRunAlertPanel(@"Restart to finish",
            @"The new title bars show up everywhere after a restart. Everything else is already done.",
            @"Restart", @"Later", nil);
        if (r == NSAlertDefaultReturn) [self restartMac];
    } else {
        BOOL logo = NO;
        for (i = 0; i < NPARTS; i++) if (verb[i] && !strcmp(PARTS[i].part, "logo")) logo = YES;
        [footer setStringValue:logo ? @"Done. The login panel changes after you log out." : @"Done."];
    }
}

- (void)applicationDidFinishLaunching:(NSNotification *)n
{
    [self buildWindow];
    [self refresh];
    [footer setStringValue:@""];
    [window makeKeyAndOrderFront:nil];
}

/* The standard About panel, with the author and the project's page as
 * credits (the copyright line comes from Info.plist). */
- (void)about:(id)sender
{
    NSMutableParagraphStyle *ps = [[[NSMutableParagraphStyle alloc] init] autorelease];
    NSMutableAttributedString *c = [[[NSMutableAttributedString alloc] init] autorelease];
    NSDictionary *plain, *bold, *link;
    [ps setAlignment:NSCenterTextAlignment];
    plain = [NSDictionary dictionaryWithObjectsAndKeys:[NSFont systemFontOfSize:11], NSFontAttributeName,
             ps, NSParagraphStyleAttributeName, nil];
    bold = [NSDictionary dictionaryWithObjectsAndKeys:[NSFont boldSystemFontOfSize:11], NSFontAttributeName,
            ps, NSParagraphStyleAttributeName, nil];
    link = [NSDictionary dictionaryWithObjectsAndKeys:[NSFont systemFontOfSize:11], NSFontAttributeName,
            ps, NSParagraphStyleAttributeName, [NSURL URLWithString:@GITHUB], NSLinkAttributeName,
            [NSColor blueColor], NSForegroundColorAttributeName,
            [NSNumber numberWithInt:NSSingleUnderlineStyle], NSUnderlineStyleAttributeName, nil];
#define ADD(s, a) [c appendAttributedString:[[[NSAttributedString alloc] initWithString:(s) attributes:(a)] autorelease]]
    ADD(@"Made by ", plain); ADD(@"Caipe97", bold);
    ADD(@"\n\nSource code, updates and bug reports:\n", plain);
    ADD(@"github.com/Caipe97/Aquafinder", link);
#undef ADD
    /* "Version 1.5" alone: by default the panel also adds CFBundleVersion, "1.5 (v1.5)" */
    [NSApp orderFrontStandardAboutPanelWithOptions:[NSDictionary dictionaryWithObjectsAndKeys:c, @"Credits",
        [@"Version " stringByAppendingString:[[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"]],
        @"ApplicationVersion", @"", @"Version", nil]];
    /* Panther's About panel shows the link but doesn't follow it on its own */
    {
        NSArray *ws = [NSApp windows];
        unsigned k;
        for (k = 0; k < [ws count]; k++) {
            NSWindow *aw = [ws objectAtIndex:k];
            NSTextView *tv = aw == window ? nil : [self textViewIn:[aw contentView]];
            if (tv) [tv setDelegate:self];
        }
    }
}

- (NSTextView *)textViewIn:(NSView *)v
{
    NSArray *sub = [v subviews];
    unsigned k;
    if ([v isKindOfClass:[NSTextView class]]) return (NSTextView *)v;
    for (k = 0; k < [sub count]; k++) {
        NSTextView *t = [self textViewIn:[sub objectAtIndex:k]];
        if (t) return t;
    }
    return nil;
}

- (BOOL)textView:(NSTextView *)tv clickedOnLink:(id)link atIndex:(unsigned)i
{
    [self openGitHub:nil];
    return YES;
}

- (void)openGitHub:(id)sender
{
    [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:@GITHUB]];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)a { return YES; }

- (void)applicationWillTerminate:(NSNotification *)n
{
    if (auth) AuthorizationFree(auth, kAuthorizationFlagDestroyRights);
}

@end

static void buildMenus(id controller)
{
    NSMenu *bar = [[[NSMenu alloc] initWithTitle:@""] autorelease];
    NSMenu *app = [[[NSMenu alloc] initWithTitle:@"Aquafinder"] autorelease];
    NSMenu *win = [[[NSMenu alloc] initWithTitle:@"Window"] autorelease];
    id it;   /* 10.3 returns id <NSMenuItem> */

    [[app addItemWithTitle:@"About Aquafinder" action:@selector(about:) keyEquivalent:@""] setTarget:controller];
    [[app addItemWithTitle:@"Aquafinder on GitHub" action:@selector(openGitHub:) keyEquivalent:@""] setTarget:controller];
    [app addItem:[NSMenuItem separatorItem]];
    [app addItemWithTitle:@"Hide Aquafinder" action:@selector(hide:) keyEquivalent:@"h"];
    [app addItem:[NSMenuItem separatorItem]];
    [app addItemWithTitle:@"Quit Aquafinder" action:@selector(terminate:) keyEquivalent:@"q"];
    it = [bar addItemWithTitle:@"" action:NULL keyEquivalent:@""];
    [bar setSubmenu:app forItem:it];

    [win addItemWithTitle:@"Close" action:@selector(performClose:) keyEquivalent:@"w"];
    [win addItemWithTitle:@"Minimize" action:@selector(performMiniaturize:) keyEquivalent:@"m"];
    it = [bar addItemWithTitle:@"" action:NULL keyEquivalent:@""];
    [bar setSubmenu:win forItem:it];

    [NSApp setMainMenu:bar];
    [NSApp setAppleMenu:app];
    [NSApp setWindowsMenu:win];
}

int main(int argc, const char *argv[])
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    Controller *c;
    [NSApplication sharedApplication];
    c = [[Controller alloc] init];
    buildMenus(c);
    [NSApp setDelegate:c];
    [NSApp run];
    [pool release];
    return 0;
}
