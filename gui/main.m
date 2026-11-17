/* Aquafinder.app: a small Panther (10.3) Cocoa front end for aquafinder.sh.
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
} Part;

static const Part PARTS[] = {
    { "finder", "finder", "Aqua Finder windows",
      "Plain Aqua instead of brushed metal, a slim 15 px bottom bar with a soft shadow, and lighter pane lines.", NO },
    { "titlebars", "titlebars appkit", "Jaguar title bars",
      "Pinstriped title bars from 10.2 in every app, see-through when inactive, and a smaller loading spinner. Needs a restart.", YES },
    { "logo", "logo", "Jaguar logo and Finder icon",
      "The Garamond \"Mac OS X\" in About This Mac and the login panel, and Jaguar's Finder icon in the Finder and the Dock.", NO },
};
#define NPARTS ((int)(sizeof PARTS / sizeof PARTS[0]))
#define S(c) [NSString stringWithCString:(c)]

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

@interface Controller : NSObject
{
    NSWindow *window;
    NSButton *box[NPARTS], *applyButton;
    NSTextField *status[NPARTS], *footer;
    NSProgressIndicator *spinner;
    int state[NPARTS];
    AuthorizationRef auth;
}
- (void)changed:(id)sender;
@end

@implementation Controller

- (NSString *)script
{
    return [[NSBundle mainBundle] pathForResource:@"aquafinder" ofType:@"sh"];
}

- (NSTextField *)label:(NSString *)s frame:(NSRect)r gray:(BOOL)gray
{
    NSTextField *t = [[[NSTextField alloc] initWithFrame:r] autorelease];
    [t setStringValue:s];
    [t setEditable:NO]; [t setSelectable:NO]; [t setBezeled:NO]; [t setDrawsBackground:NO];
    [t setFont:[NSFont systemFontOfSize:11]];
    if (gray) [t setTextColor:[NSColor disabledControlTextColor]];
    [[window contentView] addSubview:t];
    return t;
}

- (void)buildWindow
{
    float rowH = 86, h = 130 + NPARTS * rowH, y;
    int i;
    window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 440, h)
        styleMask:(NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask)
        backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"Aquafinder"];

    [self label:@"Make Panther look and fit better on small screens. Changes ask for an administrator password."
          frame:NSMakeRect(20, h - 52, 400, 34) gray:NO];

    y = h - 84;
    for (i = 0; i < NPARTS; i++, y -= rowH) {
        NSButton *b = [[[NSButton alloc] initWithFrame:NSMakeRect(18, y, 400, 20)] autorelease];
        [b setButtonType:NSSwitchButton];
        [b setTitle:S(PARTS[i].title)];
        [b setFont:[NSFont boldSystemFontOfSize:13]];
        [b setTarget:self]; [b setAction:@selector(changed:)];
        [[window contentView] addSubview:b];
        box[i] = b;
        [self label:S(PARTS[i].desc) frame:NSMakeRect(38, y - 34, 380, 30) gray:NO];
        status[i] = [self label:@"" frame:NSMakeRect(38, y - 52, 380, 16) gray:YES];
    }

    NSBox *line = [[[NSBox alloc] initWithFrame:NSMakeRect(20, 62, 400, 1)] autorelease];
    [line setBoxType:NSBoxSeparator];
    [[window contentView] addSubview:line];

    footer = [self label:@"" frame:NSMakeRect(20, 18, 250, 30) gray:YES];
    spinner = [[[NSProgressIndicator alloc] initWithFrame:NSMakeRect(276, 24, 16, 16)] autorelease];
    [spinner setStyle:NSProgressIndicatorSpinningStyle];
    [spinner setControlSize:NSSmallControlSize];
    [spinner setDisplayedWhenStopped:NO];
    [spinner setUsesThreadedAnimation:YES];
    [[window contentView] addSubview:spinner];

    applyButton = [[[NSButton alloc] initWithFrame:NSMakeRect(300, 14, 126, 32)] autorelease];
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
    case ST_ORIGINAL:  return @"Currently: not installed (Apple's original).";
    case ST_INSTALLED: return @"Currently: installed.";
    case ST_OLD:       return @"Currently: an older version is installed. Apply to update it.";
    case ST_MIXED:     return @"Currently: partly installed. Apply to finish.";
    }
    return @"Not available: a system file isn't one Aquafinder knows, so it is left alone.";
}

- (void)refresh
{
    NSString *text = [self runStatus];
    int i;
    for (i = 0; i < NPARTS; i++) {
        int st = state[i] = [self stateOf:i inText:text];
        [box[i] setEnabled:(st != ST_UNKNOWN)];
        [box[i] setState:(st == ST_INSTALLED || st == ST_OLD || st == ST_MIXED) ? NSOnState : NSOffState];
        [status[i] setStringValue:[self describe:st]];
    }
    [self changed:nil];
}

/* What Apply would do for one part: nil, @"install" or @"restore". */
- (NSString *)verbFor:(int)i
{
    if (state[i] == ST_UNKNOWN) return nil;
    if ([box[i] state] == NSOnState) return state[i] == ST_INSTALLED ? nil : @"install";
    return state[i] == ST_ORIGINAL ? nil : @"restore";
}

- (void)changed:(id)sender
{
    BOOL any = NO;
    int i;
    for (i = 0; i < NPARTS; i++) if ([self verbFor:i]) any = YES;
    [applyButton setEnabled:any];
    if (sender != nil) [footer setStringValue:any ? @"" : @"Nothing to change."];
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
    if (!any) return;
    if (![self authorize]) return;   /* cancelled at the password dialog */

    [applyButton setEnabled:NO];
    for (i = 0; i < NPARTS; i++) [box[i] setEnabled:NO];
    [footer setStringValue:@"Working..."];
    [spinner startAnimation:nil];
    [window display];
    for (i = 0; i < NPARTS; i++)
        if (verb[i]) ok = [self run:verb[i] part:S(PARTS[i].part) log:log] && ok;
    [spinner stopAnimation:nil];
    [footer setStringValue:@""];
    [self refresh];

    if (!ok) {
        NSRunAlertPanel(@"Some changes weren't made", @"%@", @"OK", nil, nil, log);
    } else if (restart) {
        int r = NSRunAlertPanel(@"Restart to finish",
            @"The title bars change in every app after a restart. Everything else has already been updated.",
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

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)a { return YES; }

- (void)applicationWillTerminate:(NSNotification *)n
{
    if (auth) AuthorizationFree(auth, kAuthorizationFlagDestroyRights);
}

@end

static void buildMenus(void)
{
    NSMenu *bar = [[[NSMenu alloc] initWithTitle:@""] autorelease];
    NSMenu *app = [[[NSMenu alloc] initWithTitle:@"Aquafinder"] autorelease];
    NSMenu *win = [[[NSMenu alloc] initWithTitle:@"Window"] autorelease];
    id it;   /* 10.3 returns id <NSMenuItem> */

    [app addItemWithTitle:@"About Aquafinder" action:@selector(orderFrontStandardAboutPanel:) keyEquivalent:@""];
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
    [NSApplication sharedApplication];
    buildMenus();
    [NSApp setDelegate:[[Controller alloc] init]];
    [NSApp run];
    [pool release];
    return 0;
}
