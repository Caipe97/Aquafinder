/* label: render text in black on white, as Cocoa draws it (Lucida Grande 11,
   the system font at the list header's size), for tools/header.py's LABEL.
   Build and run on the Panther VM (cc -o label label.m -framework Cocoa):
     label out.tiff Places 64 17 8 14
   (on Tiger the same binary with baseline 13 gives the same pixels).
   usage: label out.tiff text width height x baseline_from_top */
#import <Cocoa/Cocoa.h>
int main(int argc, char **argv) {
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    [NSApplication sharedApplication];
    NSString *text = [NSString stringWithUTF8String:argv[2]];
    float w = atof(argv[3]), h = atof(argv[4]), x = atof(argv[5]), base = atof(argv[6]);
    NSFont *f = [NSFont systemFontOfSize:11];
    NSImage *img = [[NSImage alloc] initWithSize:NSMakeSize(w, h)];
    [img lockFocus];
    [[NSColor whiteColor] set];
    NSRectFill(NSMakeRect(0, 0, w, h));
    NSDictionary *at = [NSDictionary dictionaryWithObjectsAndKeys:f, NSFontAttributeName,
                        [NSColor blackColor], NSForegroundColorAttributeName, nil];
    /* baseline 'base' rows from the top: y-up baseline = h - base */
    [text drawAtPoint:NSMakePoint(x, h - base + [f descender]) withAttributes:at];
    NSBitmapImageRep *rep = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0, 0, w, h)];
    [img unlockFocus];
    [[rep TIFFRepresentation] writeToFile:[NSString stringWithUTF8String:argv[1]] atomically:YES];
    printf("font %s descender %f ascender %f\n", [[f fontName] UTF8String], [f descender], [f ascender]);
    [pool release];
    return 0;
}
