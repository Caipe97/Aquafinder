"""Aquafinder Finder patcher: Aqua (non-metal) browser windows that keep
the toolbar and sidebar.

Patch sites are defined against the stock 10.3.9 (7W98) Finder. Other
copies -- re-prebound ones, and other builds such as 10.3.4 whose code has
moved -- are matched by masked instruction signatures, which
update_prebinding never changes; every site must match exactly once.

usage: patch.py <in-finder> <out-finder> [set,set,...]   (default: SET_NAMES)
The status bar sits under the toolbar ('topbar'), as in Jaguar; the bottom
bar layout is gone.
"""
import sys, struct
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from macho import MachO

LI_R4_METAL, LI_R4_0, LI_R4_1 = 0x38800100, 0x38800000, 0x38800001
NOP = 0x60000000

# (set, ref_addr in 10.3.9, expected word or None for "any bl/bc", action, comment)
#   action: int           -> write this literal word
#           ('bl', name)  -> bl to the stub for import `name` in this build
#           ('always',)   -> turn this conditional branch into an unconditional one
PATCHES = [
    # Never set kWindowMetalAttribute (0x100) on browser windows.
    ('nometal', 0x44f14, LI_R4_METAL, LI_R4_0, 'window init: ChangeWindowAttributes(set metal) -> set nothing'),
    ('nometal', 0x6e914, LI_R4_METAL, LI_R4_0, 'show-toolbar: ChangeWindowAttributes(set metal) -> set nothing'),
    # Square Aqua bottom corners instead of the rounded metal ones.
    ('square', 0x44f4c, LI_R4_1, LI_R4_0, 'window init: SetWindowHasRoundedCorners(1) -> 0'),
    ('square', 0x6e8f8, LI_R4_1, LI_R4_0, 'show-toolbar: SetWindowHasRoundedCorners(1) -> 0'),
    # View background eraser (status bar etc.) always takes the Aqua
    # SetThemeBackground+EraseRect branch instead of painting metal.
    ('statusbar', 0x23b0c, 0x419e0084, ('always',), 'EraseViewBackground: beq aqua -> b aqua'),
    # Sidebar divider (and the gap it leaves while dragged): it showed the
    # window's metal; nothing erases it in an Aqua window. Both its draw
    # routine and the splitter repaint draw inside a QDBeginCGContext bracket,
    # where QuickDraw erasing is never seen, so each `bl GetWindowPort` that
    # opens the bracket goes through DividerErase first, which erases the
    # divider white (cave.build_divider_erase, placed in the dead metal
    # branch of EraseViewBackground, see place_divider_erase).
    ('gap', 0x22420, None, ('bl_divider',), 'divider draw: bl GetWindowPort -> bl DividerErase'),
    ('gap', 0x4e6bc, None, ('bl_divider',), 'splitter repaint: bl GetWindowPort -> bl DividerErase'),
    ('gap', 0x4e7ac, None, NOP, 'splitter repaint: bl DrawWindowMetal... -> nop (erased already)'),
    # The divider, drawn like the column view's dividers (Jaguar's too): a
    # 15 px gray gradient with the || grip near its bottom. Its frame (the
    # rect at view+0xd4) is 13 px instead of 7, plus the panes' 1px outset
    # columns on either side: every 7 in the window layout becomes 13.
    ('gap', 0x4816c, 0x38840007, 0x3884000d, 'layout: file pane x = sidebar + 3 + 7 -> + 13'),
    ('gap', 0x48198, 0x3884fff9, 0x3884fff3, 'layout: file pane width -= 7 -> 13'),
    ('gap', 0x48388, 0x38420007, 0x3842000d, 'layout: divider right = left + 7 -> + 13'),
    ('gap', 0x48a8c, 0x38420007, 0x3842000d, 'resize: room for the divider 7 -> 13'),
    ('gap', 0x48ab0, 0x3842fff9, 0x3842fff3, 'resize: sidebar width -= 7 -> 13'),
    ('gap', 0x48c34, 0x3be20007, 0x3be2000d, 'layout: file pane x = sidebar + 3 + 7 -> + 13'),
    ('gap', 0x48cdc, 0x3863fff9, 0x3863fff3, 'layout: widest sidebar -= 7 -> 13'),
    # With the sidebar collapsed (dragged all the way left), the divider
    # stays at the window's left edge as a handle: 5 px there, 13 now too, so
    # its gradient doesn't spill over the files.
    ('gap', 0x4839c, 0x38000005, 0x3800000d, 'layout, sidebar collapsed: divider right = 5 -> 13'),
    ('gap', 0x48c1c, 0x3bfe0005, 0x3bfe000d, 'layout, sidebar collapsed: file pane x = 1 + 5 -> + 13'),
    # The gradient and grip are the grip image (tools/grip.py: 15 x 2048,
    # grip in its bottom rows). The draw centered it in the divider; now its
    # x stays centered (15 over 13: one column out on each side), but it
    # starts at the divider's bottom, and is clipped to the divider's own
    # height, less its top row, so it never reaches the row under the status
    # bar:
    #   CGContextClipToRect(ctx, {x - 1, bottom, 15, divider height - 1})
    #   CGContextDrawImage(ctx, {x - 1, bottom, 15, 2048}, image)
    # (the y centering is dead now; its words compute the clip's height,
    # the divider's minus its top row: the row under the status bar's line
    # stays white, as above the column view's dividers)
    ('gap', 0x22534, 0xd121007c, 0xed8c0028, 'grip draw: height = image height -> fsubs f12,f12,f0 (h - 0.5)'),
    ('gap', 0x22538, 0xed8c5838, 0xed8c0028, 'grip draw: y centering -> fsubs f12,f12,f0 (h - 1)'),
    ('gap', 0x22540, 0xc0010074, 0xd181007c, 'grip draw: lfs f0,y -> stfs f12,height (clip: h - 1)'),
    ('gap', 0x22550, 0xd0010074, 0x7c9d84aa, 'grip draw: y += centering -> lswi r4,r29,16 (the clip rect)'),
    ('gap', 0x22554, 0x801e0000, ('bl_new', '_CGContextClipToRect'), 'grip draw: -> bl CGContextClipToRect'),
    ('gap', 0x22558, 0x7cbd84aa, 0x80610044, 'grip draw: -> lwz r3,ctx'),
    ('gap', 0x2255c, 0x7ca285aa, 0x7c9d84aa, 'grip draw: -> lswi r4,r29,16 (the image rect)'),
    ('gap', 0x22560, 0x7c080378, 0x3ce04500, 'grip draw: -> lis r7,0x4500 (height 2048.0f)'),
    ('gap', 0x22564, 0x7c8284aa, 0x811e0000, 'grip draw: -> lwz r8,image'),
    # No pane outlines: the gradient's own edges are the only lines.
    ('gap', 0x22584, None, NOP, "divider draw: outline the sidebar -> nothing"),
    ('gap', 0x22594, None, NOP, "divider draw: outline the file pane -> nothing"),
    # The status bar's erase: the Aqua branch jumps to cave.build_topbar
    # (placed in the free space at the end of __TEXT): the Aqua erase, the
    # toolbar's pinstripes, plus Jaguar's 1px lines above and below the bar.
    ('shadow', 0x23b90, 0x38600034, ('cave',), 'status bar erase: li r3,0x34 -> b <bar routine>'),
    # Softer 1px lines: the loads of the 0.6 gray (153) read 212/255 (as
    # Jaguar's pane borders) from the cave instead.
    ('softlines', 0x2d6f4, 0xc022fef4, ('lfs_gray', 'gray'), 'pane frame fill gray 0.6 -> 212/255'),
    ('softlines', 0x19fac0, 0xc022fef4, ('lfs_gray', 'gray'), 'framed box stroke gray 0.6 -> 212/255'),
    # Bottom bar 15 rows instead of 18, the height of the resize handle (no
    # white rows above it; the file list gains 3 rows). The window layout
    # subtracts this from the content height when the bar is at the bottom:
    # 14, so the panes overlap the bar's top row and their 1px bottom border
    # is that row (212, as in Jaguar). The list's scroll bar then ends right
    # above the resize handle, with no extra line between them.
    # ('topbar' replaces the layout's 14 and leaves the bottom rect branch dead.)
    ('slimbar', 0x48958, 0x38000012, 0x3800000e, 'window layout: bottom bar height 18 -> 15, panes overlap its top row'),
    ('slimbar', 0x2ae30, 0x3842ffee, 0x3842fff1, 'status bar rect: top = bottom - 18 -> - 15'),
    ('slimbar', 0x2ae48, 0x38420012, 0x3842000f, 'status bar rect: bottom = top + 18 -> + 15'),
    # loading spinner (16x16 theme art, drawn bottom-aligned in its rect): the
    # rect ended 2 rows below the 15-row bar. Bottom = top + 14 puts the
    # canvas on the border line + bar; the theme's arrows are shrunk to 13 px
    # (theme.shrink_frames) so they sit on bar rows 1..13.
    ('slimbar', 0x1605c, 0x39290010, 0x3929000e, 'status bar spinner: bottom = top + 16 -> + 14'),
    # With the bar at the bottom, the panes' content view is one column wider
    # than the window, so the panes' right border line falls outside it and
    # the list's scroll bar ends on the window edge, in line with the resize
    # handle below it (as in Aqua windows). r28 = 1 when the bar is at the
    # bottom, 0 otherwise; the width is never negative, so no sign extension.
    ('slimbar', 0x48974, 0x7c840734, 0x7c84e214, 'window layout: content width -> width + (bar at bottom)'),
    # The status bar under the toolbar, as in Jaguar, instead of at the
    # bottom. Browser windows use the top status bar that windows without a
    # toolbar already have (20 rows, full width); the panes start below it
    # and run to the window bottom, where the resize handle sits in the list's
    # scroll bar corner as in any Aqua window. Needs 'shadow' and 'slimbar'.
    ('topbar', 0x2ae10, 0x419e0060, ('always',), 'status bar rect: beq bottom rect -> b top rect'),
    ('topbar', 0x488c4, 0x409e0014, 0x60000000, 'window layout: top offset for the bar in browser windows too'),
    # replaces slimbar's 14 (applied first): content height = rest + 1, so the
    # panes' bottom border falls outside the window, like the right one
    ('topbar', 0x48958, 0x3800000e, 0x3800ffff, 'window layout: bottom bar height 14 -> -1'),
    # The icon view's scroller reclaims the resize handle's corner when the
    # window has a toolbar (its bottom bar held the handle); leave it free as
    # without a toolbar, so the scroll bar stops above the handle.
    ('topbar', 0x3cd50, 0x809f02bc, 0x38800000, 'icon view scroller: reclaim corner = has toolbar -> 0'),
    # (plus build_topbar_fix/write_topbar_fix: the sidebar divider's drawing, 20 rows low otherwise)
    # The Action and Path toolbar items are 50 px wide (their min/max size
    # functions), but draw their 46 px image at x = 0, so 4 empty columns
    # followed each: 13 px to the next item instead of the 9 everywhere else.
    # With the capsule buttons (toolbar.py) that showed; size them to their image.
    ('toolbar', 0x2bf0c, 0x3c404248, 0x3c404238, 'toolbar item size: width 50.0 -> 46.0 (min and max)'),
    ('toolbar', 0x103284, 0x3c404248, 0x3c404238, 'toolbar item size: width 50.0 -> 46.0 (min and max)'),
    # Back and Forward: Jaguar's round buttons touched (2 px apart) in their
    # 26 px slots. Each slot is 28 px now (the images pad their circle on
    # the outer side, toolbar.py), so they're 6 px apart, and the item is
    # 56 px. The click goes to Back or Forward by the item's midpoint, so
    # that follows.
    ('toolbar', 0x2beb4, 0x3c004250, 0x3c004260, 'Back/Forward item size: width 52.0 -> 56.0'),
    ('toolbar', 0x526c8, 0x3c0041d0, 0x3c0041e0, 'Back/Forward draw: slot width 26.0 -> 28.0'),
    # The View control in an inactive window: each segment's image index is
    # its first + state, and with the window inactive (or the control
    # disabled) the state is 1 for the selected segment, else 0, the normal
    # image, drawn as in the active window, while the other items draw
    # their disabled images, at 50%. A segment now has 6 images (see
    # place_view_loader): 0 inactive, 1 selected and inactive (both at 50%,
    # toolbar.py), 2 pressed, 3 selected, 4 selected (Graphite), 5 normal.
    ('toolbar', 0x25c98, 0x38400000, 0x38400005, 'View image: normal state 0 -> 5 (0: inactive window)'),
]
# 'toolbar' (with place_view_loader): the View control's image loader and
# the first image id of each segment (VIEW_DRAW_IDS: lis r9,hi; addi r9,r9,lo
# -> 3 halfwords, read by the draw loop).
VIEW_LOADER_LAST = 0x4c48c     # the loader's 14th block (li r4,0x21a5 at +0xc); the 15th follows
VIEW_LOADER_LANDING = 0x4c570  # its exception landing pad, right after the 15th
VIEW_LOADER_DONE = 0x4c58c     # its epilogue
VIEW_DRAW_IDS = 0x52824        # View draw: addi r9,r9,-0x5d4 (after lis r9,0x2a at -8)
VIEW_IDS = (8600, 8605, 8610)
VIEW_IDS_NEW = (8600, 8606, 8612)
VIEW_IMAGES = 18
VIEW_ANCHORS = [VIEW_LOADER_LAST, VIEW_LOADER_LANDING, VIEW_LOADER_DONE, VIEW_DRAW_IDS]
SET_NAMES = ['nometal', 'square', 'statusbar', 'gap', 'shadow', 'softlines', 'slimbar', 'topbar', 'toolbar', 'barupdate']
# The sidebar styles, off by default (options of the finder part, one at a
# time; none is the plain sidebar):
#   'stripes'  a pinstriped sidebar with a slim, shadowed divider: Panther
#              10.3.9 (STRIPES_*) and Tiger 10.4.11 (TIGER_STRIPES_PATCHES)
#   'header'   a white sidebar under an Aqua list header ("Places", as the file
#              list's), and a 1 px line for a divider (HEADER_*)
#   'well'     the sidebar as a white inset list on the window's pinstripes,
#              framed like an Aqua list box, and a 1 px line by the files (WELL_*)
# 'header' and 'well' build on 'stripes'' layout (no margin around the file
# pane, the divider's image centered); 'header' also on its 7 px divider.
STYLE_SET_NAMES = ['stripes', 'header', 'well']
OPTIONAL_SET_NAMES = STYLE_SET_NAMES


def style_of(names):
    """The sidebar style among `names` (None: the plain sidebar)."""
    st = [n for n in names if n in STYLE_SET_NAMES]
    assert len(st) <= 1, 'one sidebar style at a time: %s' % ', '.join(st)
    return st[0] if st else None

# Tiger 10.4.11 (8S165). Its Finder was largely rewritten (C++, HIView), so
# the 10.3.9 signatures don't find these: they are its own addresses, used
# only when every expected word matches. Sets not listed aren't ported yet.
#   - Browser windows get the metal attribute when created (class 6,
#     attributes 0x1a88095f), and again from TWindow's metal setter (sub_28980:
#     obj+0x160 ? set 0x100 : clear 0x100, then SetWindowHasRoundedCorners).
#   - No 'statusbar' set: in an Aqua window the bottom bar is already erased
#     white (Tiger has no metal branch in its view eraser). No 'slimbar'
#     either: with 'topbar' there is no bottom bar.
TIGER_PATCHES = [
    ('nometal', 0x28040, 0x60a5095f, 0x60a5085f, 'browser window: CreateNewWindow attributes 0x1a88095f -> no metal (0x100)'),
    ('nometal', 0x289a4, 0x38800100, 0x38800000, 'metal setter: ChangeWindowAttributes(set metal) -> set nothing'),
    ('square',  0x289d0, 0x38800001, 0x38800000, 'metal setter: SetWindowHasRoundedCorners(1) -> 0'),
    # The status bar under the toolbar, as in Jaguar: browser windows use the
    # top bar that windows without a toolbar have ({0, 0, w, 20}), and the
    # panes start below it and run to the window bottom, where the resize
    # handle sits in the list's scroll bar corner.
    ('topbar',  0x28db8, 0x41be005c, 0x4800005c, 'status bar rect: toolbar window -> bottom rect; b top rect'),
    # 19 rows, under the toolbar's own 1px line: line, 18 stripes ('shadow'), line
    ('topbar',  0x28e28, 0x3c4041a0, 0x3c404198, 'status bar rect: height 20.0 -> 19.0'),
    # The panes' split container (sub_2d0f8) was {0, 0, w, h - bar}: always
    # take the bar's rect and start the container at y = bar height.
    ('topbar',  0x2d130, 0x801d0164, 0x38400000, 'pane container: li r2,0'),
    ('topbar',  0x2d134, 0x38400000, 0x90410040, 'pane container: stw r2,x'),
    ('topbar',  0x2d138, 0x90410044, 0x38610050, 'pane container: addi r3,r1,0x50'),
    ('topbar',  0x2d13c, 0x90410040, 0x7fa4eb78, 'pane container: mr r4,window'),
    ('topbar',  0x2d140, 0x2f800001, 0x4bffbc3d, 'pane container: bl status bar rect (empty if hidden)'),
    ('topbar',  0x2d144, 0x41be0020, 0xc1a1005c, 'pane container: lfs f13,bar height'),
    ('topbar',  0x2d148, 0x38610050, 0xc001004c, 'pane container: lfs f0,height'),
    ('topbar',  0x2d14c, 0x7fa4eb78, 0xec006828, 'pane container: fsubs f0,f0,f13'),
    ('topbar',  0x2d150, 0x4bffbc2d, 0xd001004c, 'pane container: height -= bar height'),
    ('topbar',  0x2d154, 0xc001004c, 0xd1a10044, 'pane container: y = bar height'),
    ('topbar',  0x2d158, 0xc1a1005c, NOP,        'pane container: nop'),
    ('topbar',  0x2d15c, 0xec006828, NOP,        'pane container: nop'),
    ('topbar',  0x2d160, 0xd001004c, NOP,        'pane container: nop'),
    # The bar's HIView layout bindings in a toolbar window: top and bottom
    # bound to the window's bottom (kind 2), so every resize moved it back
    # down under the panes; bind them to the top (1) as without a toolbar.
    ('topbar',  0x2f660, 0x38800002, 0x38800001, 'status bar layout: top binding max -> min'),
    ('topbar',  0x2f66c, 0x38800002, 0x38800001, 'status bar layout: bottom binding max -> min'),
    # The bar's Draw fills its background, then draws the 163 gray bottom
    # line; the fill goes through cave.build_tiger_bar (placed in the free
    # space at the end of __TEXT) for Jaguar's pinstripes and its top line.
    ('shadow',  0x42e48, 0x4bffc519, ('bl_cave', 'bar'), 'status bar draw: bl background fill -> bl <bar routine>'),
    # The sidebar divider, as the column view's (Jaguar's): 13 px wide
    # instead of 7, drawn by cave.build_tiger_divider (the gradient and the
    # grip near its bottom) instead of Tiger's dimple, and no pane outlines:
    # the gradient's own edges are the only lines.
    ('gap',     0x2d924, 0xc022d488, 0xc022d514, 'splitter: divider width 7.0 -> 13.0 (an existing 13.0f)'),
    ('gap',     0x3f24c, 0x480000b9, ('bl_cave', 'divider'), 'splitter draw: bl background + DrawDivider (dimple) -> bl <divider routine>'),
    ('gap',     0x3f29c, 0x480001ad, NOP, 'splitter draw: outline the sidebar -> nothing'),
    ('gap',     0x3f2ec, 0x4800015d, NOP, 'splitter draw: outline the file pane -> nothing'),
    # The file pane's margins in the splitter (sub_2d66c(view, pane, f1..f4),
    # f2 right, f3 top, f4 bottom) left room for its outline: 1 right, 2
    # bottom. With no outline, its scroll bars run to the window's edges and
    # the resize handle sits in their corner, as in any Aqua window. (Top 1
    # stays: the white row under the status bar's line, as Panther's.)
    ('gap',     0x2d424, 0xc082d454, 0xc082d41c, 'splitter init: file pane bottom margin 2.0 -> 0.0'),
    ('gap',     0x2d428, 0xfc400890, 0xfc402090, 'splitter init: file pane right margin 1.0 -> 0.0 (fmr f2,f4)'),
    # The search window's scope bar (Servers, Computer, ...; sub_1a7c54) was
    # black at 10% over white (229) above its 138 bottom line: the same
    # pinstripes as the status bar instead (the bar routine stripes all rows
    # above the view's bottom one, where the line still goes).
    ('shadow',  0x1a7c98, 0x4be979c9, 0x7f63db78, 'scope bar draw: mr r3,view'),
    ('shadow',  0x1a7c9c, 0x7fa3eb78, 0x7f84e378, 'scope bar draw: mr r4,ctx'),
    ('shadow',  0x1a7ca0, 0x7f64db78, ('bl_cave', 'bar'), 'scope bar draw: 10% black fill -> bl <bar routine>'),
    ('shadow',  0x1a7ca4, 0x4be6c0a5, 0x3c400032, 'scope bar draw: lis r2,0x32'),
    ('shadow',  0x1a7ca8, 0x7f83e378, 0xc3e2d434, 'scope bar draw: lfs f31,1.0 (used by the line below)'),
    ('shadow',  0x1a7cac, 0x3c400032, NOP,        'scope bar draw: nop'),
    ('shadow',  0x1a7cb0, 0x7c9d84aa, NOP,        'scope bar draw: nop'),
    ('shadow',  0x1a7cb4, 0xc3e2d434, NOP,        'scope bar draw: nop'),
    ('shadow',  0x1a7cb8, 0x4804b709, NOP,        'scope bar draw: nop'),
    # Lighter 1px lines, 212 as Jaguar's pane borders (cave.build_tiger_line's
    # RGBA gray): the scope bar's (and its sibling view's, sub_1a8bb8) bottom
    # line, 138 -> 212, and the frame the search window's path pane strokes
    # (sub_1b8484; its top edge is the line above the pane), 158 -> 212.
    ('softlines', 0x1a7cc4, 0xc002d5a4, ('lfs_cave', 'line'), 'scope bar line gray 0.54 -> 212/255'),
    ('softlines', 0x1a8bc4, 0xc002d5a4, ('lfs_cave', 'line'), 'bar line gray 0.54 -> 212/255'),
    ('softlines', 0x1b85d0, 0x3884d288, ('addi_cave', 'line'), 'path pane frame: stroke color 158 gray -> 212 (RGBA)'),
    # Jaguar's toolbar buttons (toolbar.py TIGER_IDS, cave.build_tiger_toolbar):
    # Back/Forward and View are HISegmentedViews (sub_34650 makes both); as
    # their segments are counted, each gets an event handler that draws
    # Jaguar's images (28 px slots for Back and Forward, 26 for the View
    # segments) and hit-tests by them. The items' min/max sizes follow:
    # Back/Forward 53 -> 56 (2 x 28), View 81 -> 78 (3 x 26). Action and Path
    # draw their 46 px images in 46 px items already (no 'toolbar' fix there).
    ('toolbar', 0x346e8, 0x481c36c9, ('bl_cave', 'segviews'), 'segmented view: bl HISegmentedViewSetSegmentCount -> bl <install Jaguar draw>'),
    # A segment turned on or off (sub_3a198, e.g. Forward after Back and a
    # new folder) redraws the whole view, not just HIToolbox's own segment rect.
    ('toolbar', 0x3a1e0, 0x481bdb50, ('b_cave', 'segenable'), 'segment enable: b HISegmentedViewSetSegmentEnabled -> b <set it, redraw the view>'),
    ('toolbar', 0x343d4, 0x3c004250, 0x3c004260, 'Back/Forward view frame: width 52.0 -> 56.0'),
    ('toolbar', 0x35d88, 0x3c004254, 0x3c004260, 'Back/Forward item size: width 53.0 -> 56.0 (min and max)'),
    ('toolbar', 0x35d9c, 0x3c0042a2, 0x3c00429c, 'View item size: width 81.0 -> 78.0 (min and max)'),
]
TIGER_SET_NAMES = ['nometal', 'square', 'topbar', 'shadow', 'gap', 'softlines', 'toolbar']
# 'stripes' on Tiger (cave.build_tiger_stripes): the sidebar's back color
# fills (its Draw, sub_3f6e4, and an item's while one is dragged, sub_16de60)
# stripe instead; scrolling redraws it instead of copying its pixels; the
# sidebar's margins in the splitter, and the file pane's left and top ones,
# go (the splitter's left part is striped under them); the divider keeps its
# stock 7 px and is drawn as Panther's stripes divider.
TIGER_STRIPES_PATCHES = [
    ('stripes', 0x3f7bc, 0x481b3c05, ('bl_cave', 'sidefill'), 'sidebar draw: back color fill -> bl <SideFill> (pinstripes)'),
    ('stripes', 0x16deb8, 0x48085509, ('bl_cave', 'itemfill'), 'sidebar item draw (dragging): back color fill -> bl <ItemFill> (pinstripes)'),
    ('stripes', 0x2e424, 0x480000e9, ('bl_cave', 'sopaque'), 'scroll: bl opaque? -> bl <never for the sidebar> (redraw, no pixel copy)'),
    ('stripes', 0x2d3f4, 0xc022d434, 0xc022d41c, 'splitter init: sidebar margins 1.0 -> 0.0'),
    ('stripes', 0x2d400, 0xc082d454, 0xc082d41c, 'splitter init: sidebar bottom margin 2.0 -> 0.0'),
    ('stripes', 0x2d418, 0xc022d434, 0xc022d41c, 'splitter init: file pane left and top margins 1.0 -> 0.0'),
]
# 'gap' entries that 'stripes' replaces (None: left as it is)
TIGER_STRIPES_OVERRIDES = {
    0x2d924: None,                                  # divider width: the stock 7.0
    0x3f24c: ('bl_cave', 'sdivider'),               # the stripes divider
}
# 'header' on Tiger (cave.build_tiger_header): the sidebar's margins in the
# splitter go but the top one, the header's rows - 1 (its first row is the
# status bar's last, the top edge below); the file pane's top margin is -1
# (its own first row hidden under that edge) and its left one goes; the
# divider keeps its stock 7 px, drawn as a 1 px line, with the header.
# The status bar's last row, the top edge of 'header' and 'well' (cave.EDGE_*,
# cave.build_tiger_edge): its line fill goes to the edge routine.
TIGER_EDGE_FILL = 0x42ef0              # status bar draw: bl CGContextFillRect (its bottom line)
TIGER_HEADER_PATCHES = [
    ('header', 0x2d3f4, 0xc022d434, 0xc022d41c, 'splitter init: sidebar margins 1.0 -> 0.0'),
    ('header', 0x2d400, 0xc082d454, 0xc082d41c, 'splitter init: sidebar bottom margin 2.0 -> 0.0'),
    ('header', 0x2d408, 0xfc600890, ('lfs_cave_reg', 3, 'hmargin'), 'splitter init: sidebar top margin -> header rows - 1 (lfs f3)'),
    ('header', 0x2d418, 0xc022d434, 0xc022d41c, 'splitter init: file pane left (and top) margins 1.0 -> 0.0'),
    ('header', 0x2d42c, 0xfc600890, ('lfs_cave_reg', 3, 'hmone'), 'splitter init: file pane top margin -1.0 (under the top edge)'),
    ('header', TIGER_EDGE_FILL, 0x481b04d1, ('bl_cave', 'edge'), 'status bar draw: its bottom line -> bl <edge routine>'),
]
TIGER_HEADER_OVERRIDES = {
    0x2d924: None,                                  # divider width: the stock 7.0
    0x3f24c: ('bl_cave', 'hdivider'),               # the line and the header
}
# 'well' on Tiger (cave.build_tiger_well): the sidebar's margins in the
# splitter are the well's (left, top, bottom; right 1, the frame's line), the
# file pane's go; the divider is the margin wide.
TIGER_WELL_PATCHES = [
    ('well', 0x2d3f4, 0xc022d434, ('lfs_cave_reg', 1, 'wmargin'), 'splitter init: sidebar margins 1.0 -> the margin (left)'),
    ('well', 0x2d400, 0xc082d454, ('lfs_cave_reg', 4, 'wmargin'), 'splitter init: sidebar bottom margin 2.0 -> the margin'),
    ('well', 0x2d404, 0xfc400890, 0xc042d434, 'splitter init: sidebar right margin -> 1.0 (lfs f2,1.0)'),
    ('well', 0x2d408, 0xfc600890, 0xc062d41c, 'splitter init: sidebar top margin -> 0.0 (the frame top is the top edge)'),
    ('well', 0x2d418, 0xc022d434, 0xc022d41c, 'splitter init: file pane left margin 1.0 -> 0.0'),
    ('well', 0x2d42c, 0xfc600890, ('lfs_cave_reg', 3, 'wmone'), 'splitter init: file pane top margin -1.0 (under the top edge)'),
    ('well', TIGER_EDGE_FILL, 0x481b04d1, ('bl_cave', 'edge'), 'status bar draw: its bottom line -> bl <edge routine>'),
]
TIGER_WELL_OVERRIDES = {
    0x2d924: ('lfs_cave_reg', 1, 'wmargin'),        # divider width: the margin
    0x3f24c: ('bl_cave', 'wdivider'),               # stripes, line and frame
}
TIGER_STYLE_OVERRIDES = {'stripes': TIGER_STRIPES_OVERRIDES, 'header': TIGER_HEADER_OVERRIDES,
                         'well': TIGER_WELL_OVERRIDES}


def is_tiger(m):
    for _, addr, expect, _, _ in TIGER_PATCHES:
        off = m.addr2off(addr)
        if off is None or struct.unpack_from('>I', m.data, off)[0] != expect:
            return False
    return True


def place_tiger_cave(m, data, names, quiet):
    """Write the routines of the sets in `names` ('shadow': cave.build_tiger_bar,
    'gap': cave.build_tiger_divider, or with 'stripes' cave.build_tiger_stripes
    instead; 'softlines': cave.build_tiger_line, its constants only;
    'toolbar': cave.build_tiger_toolbar) into the
    free space at the end of __TEXT, one after the other; returns {'bar':
    entry, 'divider': entry, 'line': RGBA gray, 'line_gray': float gray,
    'segviews' ('toolbar'), and with 'stripes' its entries: 'sidefill',
    'itemfill', 'sdivider', 'sopaque'}."""
    import cave
    last = max(x['addr'] + x['size'] for x in m.sections if x['seg'] == '__TEXT')
    seg = [x for x in m.segments if x['name'] == '__TEXT'][0]
    end = seg['vmaddr'] + seg['filesize']
    stubs = {nm: stub_addr(m, nm) for nm in cave.TIGER_BAR_STUBS + cave.TIGER_STRIPES_STUBS + cave.TIGER_TOOLBAR_STUBS
             + cave.TIGER_HEADER_STUBS + cave.TIGER_EDGE_STUBS + cave.TIGER_WELL_STUBS + cave.TIGER_WELL_EDGE_STUBS}
    import header
    caddr, entries = (last + 15) & ~15, {}
    build_header = lambda c, st: cave.build_tiger_header(c, st, header.HEADER_ID, header.HEIGHT, header.HEADER_WIDTH)
    if 'well' in names:                    # its divider updates, in the outline routine's dead code
        ohead, oend = cave.TIGER_OUTLINE_FN
        w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
        assert w(ohead) == 0x7c0802a6 and w(ohead + 4) == 0xbf01ffd8 and w(oend) == 0x7c0802a6, 'pane outline routine'
        code, ent = cave.build_tiger_divupdate(ohead, {nm: stub_addr(m, nm) for nm in cave.TIGER_DIVUPDATE_STUBS})
        assert len(code) <= oend - ohead
        data[m.addr2off(ohead):m.addr2off(ohead) + len(code)] = code
        for k in range(ohead + len(code), oend, 4):
            struct.pack_into('>I', data, m.addr2off(k), 0x60000000)
        entries.update(ent)
        if not quiet:
            print('well      %08x file+%06x  %d bytes (divider updates) in the pane outline routine, %d free' % (
                ohead, m.addr2off(ohead), len(code), oend - ohead - len(code)))
    build_well = lambda c, st: cave.build_tiger_well(c, st, WELL_MARGIN, entries.get('divupdate'))
    style = style_of(names)
    if style == 'well':                    # the well's edge reads the divider (cave.build_tiger_well_edge)
        assert data_tail_free(m, cave.TIGER_BAR_STASH, 4), 'no room for the status bar stash'
        build_edge = lambda c, st: cave.build_tiger_well_edge(c, st, WELL_MARGIN)
    else:
        build_edge = lambda c, st: cave.build_tiger_edge(c, st, cave.EDGE_HEADER)
    build_bar = lambda c, st: cave.build_tiger_bar(c, st, stash=cave.TIGER_BAR_STASH if style == 'well' else None)
    for key, setname, build in (('bar', 'shadow', build_bar),
                                ('divider', 'gap', cave.build_tiger_divider),
                                ('line', 'softlines', cave.build_tiger_line),
                                ('stripes', 'stripes', cave.build_tiger_stripes),
                                ('header', 'header', build_header),
                                ('well', 'well', build_well),
                                ('edgecave', style if style in ('header', 'well') else None, build_edge),
                                ('toolbar', 'toolbar', cave.build_tiger_toolbar)):
        if setname not in names or (key == 'divider' and style_of(names)):
            continue
        code, entries[key], *data_addr = build(caddr, stubs)
        if isinstance(entries[key], dict):
            entries.update(entries[key])
            entries[key] = min(entries[key].values())
        if data_addr:
            entries[key + '_gray'] = data_addr[0]
        coff = m.addr2off(caddr)
        if len(code) > end - caddr:
            sys.exit('%s routine (%d bytes) does not fit in __TEXT padding (%d)' % (key, len(code), end - caddr))
        if any(data[coff:coff + len(code)]):
            sys.exit('__TEXT padding at %08x is not empty' % caddr)
        data[coff:coff + len(code)] = code
        if not quiet:
            print('cave      %08x file+%06x  %d bytes (%s at %08x), %d free' % (
                caddr, coff, len(code), key, entries[key], end - caddr - len(code)))
        caddr = (caddr + len(code) + 15) & ~15
    return entries


def apply_tiger(m, path_out, names, quiet):
    data = bytearray(m.data)
    style = style_of(names)
    if style:
        assert all(n in names for n in ('gap', 'topbar', 'shadow')), "'%s' needs 'gap', 'topbar' and 'shadow'" % style
    if style == 'stripes':
        import cave
        vt = m.addr2off(cave.TIGER_SIDEBAR_VTABLE + 0xe4)
        assert struct.unpack_from('>I', m.data, vt)[0] == 0x3f6e4, 'sidebar vtable not found'
    overrides = TIGER_STYLE_OVERRIDES.get(style, {})
    entries = place_tiger_cave(m, data, names, quiet)
    for name, addr, expect, new, why in TIGER_PATCHES + TIGER_STRIPES_PATCHES + TIGER_HEADER_PATCHES + TIGER_WELL_PATCHES:
        if name not in names:
            continue
        if addr in overrides:
            new = overrides[addr]
            if new is None:
                continue
            why += ' (%s)' % style
        off = m.addr2off(addr)
        cur = struct.unpack_from('>I', data, off)[0]
        if cur != expect:
            sys.exit('mismatch at %08x: %08x != expected %08x (%s)' % (addr, cur, expect, why))
        if isinstance(new, tuple) and new[0] == 'bl_cave':
            new = 0x48000001 | ((entries[new[1]] - addr) & 0x03fffffc)
        elif isinstance(new, tuple) and new[0] == 'b_cave':     # a tail call
            new = 0x48000000 | ((entries[new[1]] - addr) & 0x03fffffc)
        elif isinstance(new, tuple) and new[0] == 'cave_ptr':   # a pointer (vtable slot)
            new = entries[new[1]]
        elif isinstance(new, tuple) and new[0] == 'addi_cave':  # addi rX,rX,lo after lis rX,0x32
            disp = entries[new[1]] - 0x320000
            assert -0x8000 <= disp < 0x8000
            new = (expect & 0xffff0000) | (disp & 0xffff)
        elif isinstance(new, tuple) and new[0] == 'lfs_cave':   # lfs fX,lo(rB), rB = 0x320000
            disp = entries[new[1] + '_gray'] - 0x320000
            assert -0x8000 <= disp < 0x8000
            new = (expect & 0xffff0000) | (disp & 0xffff)
        elif isinstance(new, tuple) and new[0] == 'lfs_cave_reg':   # lfs f<reg>,lo(r2), r2 = 0x320000
            disp = entries[new[2]] - 0x320000
            assert -0x8000 <= disp < 0x8000
            new = (48 << 26) | (new[1] << 21) | (2 << 16) | (disp & 0xffff)
        struct.pack_into('>I', data, off, new)
        if not quiet:
            print('%-9s %08x file+%06x  %08x -> %08x  %s' % (name, addr, off, expect, new, why))
    # 'statusbar' and 'slimbar' have nothing to do in Tiger (no metal branch
    # in its eraser; with 'topbar' there is no bottom bar to slim)
    todo = [n for n in names if n not in TIGER_SET_NAMES + STYLE_SET_NAMES and n not in ('statusbar', 'slimbar')]
    # (every set is ported now; this only reports a set name it doesn't know)
    if todo and not quiet:
        print('Tiger 10.4.11: not ported yet, skipped: %s' % ', '.join(todo))
    open(path_out, 'wb').write(bytes(data))
    return {}


SETS = {n: {p[1]: p for p in PATCHES if p[0] == n} for n in SET_NAMES}

# Framed-box painter's metal fill section (QuickDraw erase inside a CG bracket,
# so it never showed): skipped and reused for the divider's erase entry point.
FRAMEDBOX_SKIP = 0x19faec      # mr r3,r25 ; ... ; bl EraseRgn  (17 words)
FRAMEDBOX_RESUME = 0x19fb30    # lis r29,0x32 (one-time grip image load)
FRAMEDBOX_STUB = 16            # place_divider's 4-word stub; DividerOutset follows
# The framed box is the search results' horizontal splitter (between the
# results and the path pane). After its fill it loads the grip image once
# (FRAMEDBOX_RESUME..LOADED) and draws it centered, unclipped
# (CGContextResetClip first): the 15 x 2048 divider image (tools/grip.py) made
# that a 15 px strip down the whole window. The loader loads the splitter bar
# 'PNG ' 8801 instead (grip.SPLITTER_ID), and the centered draw becomes
# cave.build_splitter_draw: the bar, clipped to the box and covering it.
FRAMEDBOX_RSRC_ID = 0x19fb4c   # li r4,0x2260 ('PNG ' 8800, the grip)
FRAMEDBOX_LOADED = 0x19fb84    # lwz r3,0(r30): r30 = &image
# (both at fixed offsets from FRAMEDBOX_RESUME: the sidebar divider has the same loader)
FRAMEDBOX_CGRECT = 0x19fc0c    # bl sub_14fb4 (the box, QD -> CG)
FRAMEDBOX_DRAWN = 0x19fc80     # right after bl CGContextDrawImage (the grip)
DIVIDER_CGRECT_CALL = 0x22500  # bl sub_14fb4 in the divider's draw routine
DIVIDER_FRAME_CALL = 0x224e0   # bl sub_1ff18 (divider frame, port coordinates)
# (10.3.9 addresses; located in other builds like the PATCHES sites)
DIVIDER_ANCHORS = [FRAMEDBOX_SKIP, FRAMEDBOX_RESUME, FRAMEDBOX_CGRECT, FRAMEDBOX_DRAWN,
                   DIVIDER_CGRECT_CALL, DIVIDER_FRAME_CALL]

# 'topbar': QD rect -> CGRect converter (sub_14fb4) and its callers that pass
# port rects (see cave.build_cgrect_port). The port entry lives in the bottom
# status bar rect branch of sub_2adc8, dead once 'topbar' always takes the top.
CGRECT_FN = 0x14fb4
CGRECT_STWU = 0x14fc4          # stwu r1,-0x60(r1): last prologue word
CGRECT_TOP = 0x14fec           # lha r0,0x48(r1): window content top
CGRECT_PORT_CALLERS = [0x207e0,   # pane border lines, drawn by the divider
                       0x4e710]   # splitter repaint while dragging the divider
BOTTOMBAR_DEAD = (0x2ae14, 0x2ae70)   # after 'topbar's b at 0x2ae10, up to the top rect
TOPBAR_ANCHORS = [CGRECT_STWU, CGRECT_TOP, BOTTOMBAR_DEAD[0]] + CGRECT_PORT_CALLERS

# 'barupdate': browser windows draw their status bar on updates too, from
# the end of the sidebar splitter's DrawSelf (cave.build_splitter_bar; its
# head after the splitter bar draw, so it needs 'gap', its tail after the
# bar routine at the end of __TEXT, so it needs 'shadow').
SPLITTER_DRAWSELF_END = 0x225e8   # TSidebarSplitter::DrawSelf: its final blr
SHOW_BAR_LOAD = 0x52498        # Show: lwz r3,0x1f4(r31) (window->statusBar), after ShowSelf
SHOW_BAR_HIDDEN = 0x524a4      # Show: lwz r0,0x248(r31) (1: bar hidden)
SHOW_BAR_DRAW = 0x524c0        # Show: b BAR_DRAW
BAR_DRAW = 0x21c8c             # the status bar's draw
BARUPDATE_ANCHORS = [SPLITTER_DRAWSELF_END, SHOW_BAR_LOAD, SHOW_BAR_HIDDEN, SHOW_BAR_DRAW, BAR_DRAW]
BROWSER_WINDOW_CLASS = b'17TFileViewerWindow'

REF_PATH = __file__.rsplit('/', 2)[0] + '/orig/Finder-10.3.9'


def mask(w):
    op = w >> 26
    if op == 18: return w & 0xfc000003      # b/bl: drop displacement
    if op == 16: return w & 0xffff0003      # bc: drop displacement
    if op == 15: return w & 0xffff0000      # lis/addis: drop immediate
    if op in (48, 50): return w & 0xffff0000   # lfs/lfd of a constant: drop displacement
    return w


def text_words(m):
    s = m.section('__text')
    return s, [struct.unpack_from('>I', m.data, s['offset'] + 4*i)[0] for i in range(s['size'] // 4)]


def locate(ref, target, names=None):
    """Map each 10.3.9 patch address to its address in `target` (identity for the
    stock file; signature match for re-prebound copies). Only the sites of the
    sets in `names` (default: all) are looked up, so an optional set's sites
    needn't exist in builds that don't use it."""
    anchors = [p[1] for p in PATCHES if names is None or p[0] in names] + DIVIDER_ANCHORS
    if names is None or 'topbar' in names:
        anchors += TOPBAR_ANCHORS
    if names is None or 'barupdate' in names:
        anchors += BARUPDATE_ANCHORS
    if names is None or 'toolbar' in names:
        anchors += VIEW_ANCHORS
    if ref.data == target.data:
        return {a: a for a in anchors}
    rs, rw = text_words(ref)
    ts, tw = text_words(target)
    tm = [mask(w) for w in tw]
    found = {}
    for a in anchors:
        i = (a - rs['addr']) // 4
        hits = []
        # symmetric context first, then left-only, then right-only, then a
        # narrow symmetric one (10.3.4 differs within 8 words of some sites)
        for lo, hi in ([(c, c) for c in range(8, 33, 4)] + [(c, 0) for c in range(8, 65, 4)] +
                       [(0, c) for c in range(8, 65, 4)] + [(4, 4)]):
            sig = [mask(w) for w in rw[i-lo:i+hi+1]]
            hits = [j + lo for j in range(len(tm) - len(sig)) if tm[j:j+len(sig)] == sig]
            if len(hits) == 1:
                break
        if len(hits) != 1:
            sys.exit('cannot uniquely locate patch site %08x: %d candidates' % (a, len(hits)))
        found[a] = ts['addr'] + 4*hits[0]
    return found


def stub_addr(m, name):
    for s in m.sections:
        if s['type'] == 8:
            for a, n in m.imports.items():
                if n == name and s['addr'] <= a < s['addr'] + s['size']:
                    return a
    sys.exit('import %s not found' % name)


def place_cave(m, data, hook, quiet, keep_last_row=False):
    """Write tools/cave.py's routine + constants into the free space at the
    end of __TEXT.
    Returns {'addr': routine, 'gray': the line gray (float)}."""
    import cave
    last = max(x['addr'] + x['size'] for x in m.sections if x['seg'] == '__TEXT')
    seg = [x for x in m.segments if x['name'] == '__TEXT'][0]
    caddr = (last + 15) & ~15
    stubs = {nm: stub_addr(m, nm) for nm in cave.STUBS_NEEDED}
    code, grays = cave.build_topbar(caddr, hook, stubs, keep_last_row=keep_last_row)
    coff = m.addr2off(caddr)
    room = seg['vmaddr'] + seg['filesize'] - caddr
    if len(code) > room:
        sys.exit('bar routine (%d bytes) does not fit in __TEXT padding (%d)' % (len(code), room))
    if any(data[coff:coff + len(code)]):
        sys.exit('__TEXT padding at %08x is not empty' % caddr)
    data[coff:coff + len(code)] = code
    if not quiet:
        print('cave      %08x file+%06x  %d bytes (routine + grays), %d free' % (
            caddr, coff, len(code), room - len(code)))
    tail = (caddr + len(code) + 15) & ~15
    return dict(grays, addr=caddr, free=(tail, seg['vmaddr'] + seg['filesize']))


def bl_target(data, m, a):
    w = w2(data, m, a)
    assert w >> 26 == 18 and w & 1, 'expected bl at %08x' % a
    disp = w & 0x03fffffc
    if disp & 0x02000000: disp -= 0x04000000
    return a + disp


def place_divider_erase(m, data, sites, quiet, style=None):
    """Write cave.build_divider_erase() into EraseViewBackground's metal
    branch, which the 'statusbar' set makes unreachable (it starts right after
    the branch we make unconditional and ends at the Aqua branch). With
    'stripes' the divider is erased with the toolbar's pinstripes, its frame
    only (the panes have no border columns then)."""
    import cave
    start, end = sites[0x23b0c] + 4, sites[0x23b90]
    ext = sites[FRAMEDBOX_SKIP] + FRAMEDBOX_STUB    # after place_divider's stub
    stubs = {nm: stub_addr(m, nm) for nm in cave.DIVIDER_STUBS}
    brush = cave.TOOLBAR_BRUSH if style in ('stripes', 'well') else cave.DIVIDER_BRUSH
    code, back = cave.build_divider_erase(start, stubs, bl_target(data, m, sites[DIVIDER_FRAME_CALL]), ext, brush,
                                          bottom_row=style == 'well')
    assert len(code) <= end - start, 'divider erase too big for the dead branch'
    off = m.addr2off(start)
    data[off:off + len(code)] = code
    if style == 'well':
        tail = cave.build_divider_outset_well(ext, back, stubs, sites[WELL_DRAWSELF_ERASE] + 4)
    else:
        tail = cave.build_divider_outset(ext, back, stubs, 0 if style else 1)
    assert ext + len(tail) <= sites[FRAMEDBOX_RESUME], 'divider outset too big for the framed-box section'
    data[m.addr2off(ext):m.addr2off(ext) + len(tail)] = tail
    if not quiet:
        print('divider   %08x file+%06x  %d bytes (DividerErase) in dead metal branch, %d free' % (
            start, off, len(code), end - start - len(code)))
        print('divider   %08x file+%06x  %d bytes (DividerOutset) in the skipped framed-box section, %d free' % (
            ext, m.addr2off(ext), len(tail), sites[FRAMEDBOX_RESUME] - ext - len(tail)))
    return start


def place_divider(m, data, sites, quiet, cg_entry=None):
    """Skip the framed-box painter's metal fill section (a QuickDraw erase
    inside a CG bracket, never seen). cg_entry ('topbar'): the divider's QD ->
    CG rect call goes to the converter's port-rect entry."""
    import cave
    ref = MachO(REF_PATH)
    def w(mm, a): return struct.unpack_from('>I', mm.data, mm.addr2off(a))[0]
    skip, resume = sites[FRAMEDBOX_SKIP], sites[FRAMEDBOX_RESUME]
    assert resume - skip == FRAMEDBOX_RESUME - FRAMEDBOX_SKIP, 'framed-box section has a different length'
    for k in range(0, resume - skip, 4):           # code must match the stock 10.3.9 code
        assert mask(w(m, skip + k)) == mask(w(ref, FRAMEDBOX_SKIP + k)), 'framed-box code differs at %08x' % (skip + k)
    import grip
    rid, loaded = resume + FRAMEDBOX_RSRC_ID - FRAMEDBOX_RESUME, resume + FRAMEDBOX_LOADED - FRAMEDBOX_RESUME
    drawn = sites[FRAMEDBOX_DRAWN]
    for k in range(0, loaded - resume, 4):        # the loader's instructions (its globals move between builds)
        assert w(m, resume + k) >> 26 == w(ref, FRAMEDBOX_RESUME + k) >> 26, 'framed-box loader differs at %08x' % (resume + k)
    assert drawn - loaded == FRAMEDBOX_DRAWN - FRAMEDBOX_LOADED, 'framed-box grip draw has a different length'
    assert w(m, rid) == 0x38800000 | grip.GRIP_ID and w(m, drawn - 4) >> 26 == 18, 'unexpected framed-box grip code'
    stub = cave.Asm(skip)
    stub.li(30, 1)                                 # r30 = 1: the loader's 'loaded' flag
    stub.li(0, 0)
    stub.stw(0, 0xa0, 1)                           # no region -> nothing to dispose
    stub.b(resume)
    code = stub.assemble()
    assert len(code) == FRAMEDBOX_STUB
    off = m.addr2off(skip)
    data[off:off + len(code)] = code
    struct.pack_into('>I', data, m.addr2off(rid), 0x38800000 | grip.SPLITTER_ID)
    bar = cave.build_splitter_draw(loaded, grip.SPLITTER_WIDTH, bl_target(data, m, sites[FRAMEDBOX_CGRECT]), drawn,
                                   {nm: stub_addr(m, nm) for nm in cave.SPLITTER_STUBS})
    assert loaded + len(bar) <= drawn, 'splitter draw too big for the framed box\'s grip draw'
    data[m.addr2off(loaded):m.addr2off(loaded) + len(bar)] = bar
    if not quiet:
        print('divider   %08x file+%06x  framed-box metal section skipped' % (skip, off))
        print('divider   %08x file+%06x  framed box loads \'PNG \' %d (splitter bar) instead of %d' % (
            rid, m.addr2off(rid), grip.SPLITTER_ID, grip.GRIP_ID))
        print('divider   %08x file+%06x  %d bytes (splitter bar draw) in the framed box\'s grip draw, %d free' % (
            loaded, m.addr2off(loaded), len(bar), drawn - loaded - len(bar)))
    free = (loaded + len(bar) + 15) & ~15, drawn
    if cg_entry:
        hook = sites[DIVIDER_CGRECT_CALL]
        hw = w2(data, m, hook)
        assert hw >> 26 == 18 and hw & 1, 'expected bl at %08x' % hook
        struct.pack_into('>I', data, m.addr2off(hook), 0x48000001 | ((cg_entry - hook) & 0x03fffffc))
        if not quiet:
            print('topbar    %08x file+%06x  %08x -> bl %08x  divider draw: QD->CG rect -> port-rect entry' % (
                hook, m.addr2off(hook), hw, cg_entry))
    return free


def w2(data, m, a):
    return struct.unpack_from('>I', data, m.addr2off(a))[0]


def vtables_of(m, class_name):
    """Primary vtable addresses (as stored in objects: the first function
    slot) of the class whose mangled name is class_name: typeinfo name
    string -> typeinfo -> vtable (offset to top 0)."""
    d = m.data
    def words(value):
        out = []
        for s in m.sections:
            if s['seg'] == '__DATA' and s['offset'] and s['type'] in (0, 11):
                for k in range(0, s['size'] - 3, 4):
                    if struct.unpack_from('>I', d, s['offset'] + k)[0] == value:
                        out.append(s['addr'] + k)
        return out
    out, i = [], d.find(class_name + b'\0')
    while i >= 0:
        if d[i - 1:i] == b'\0':
            for ti in [a - 4 for a in words(m.off2addr(i))]:
                out += [v + 4 for v in words(ti) if struct.unpack_from('>i', d, m.addr2off(v - 4))[0] == 0]
        i = d.find(class_name + b'\0', i + 1)
    return out


def place_barupdate(m, data, sites, free, tail, quiet):
    """The splitter DrawSelf's blr -> b cave.build_splitter_bar (see
    SPLITTER_DRAWSELF_END). free: (start, end) after the splitter bar draw;
    tail: (start, end) after the bar routine."""
    import cave
    end, bar_draw = sites[SPLITTER_DRAWSELF_END], sites[BAR_DRAW]
    assert w2(data, m, end) == 0x4e800020 and w2(data, m, end - 4) == 0xcbe1fff8, 'unexpected splitter DrawSelf epilogue'
    assert w2(data, m, sites[SHOW_BAR_LOAD]) == 0x807f0000 | cave.BAR_FIELD, 'window->statusBar is elsewhere'
    assert w2(data, m, sites[SHOW_BAR_HIDDEN]) == 0x801f0000 | cave.BAR_HIDDEN_FIELD, 'bar hidden flag is elsewhere'
    assert bl_target_any(data, m, sites[SHOW_BAR_DRAW]) == bar_draw, 'Show does not draw the bar'
    vt = vtables_of(m, BROWSER_WINDOW_CLASS)
    assert len(vt) == 1, 'browser window vtable: %d found' % len(vt)
    head, tl = cave.build_splitter_bar(free[0], tail[0], vt[0], bar_draw,
                                       {nm: stub_addr(m, nm) for nm in cave.SPLITTER_BAR_STUBS})
    assert free[0] + len(head) <= free[1] and tail[0] + len(tl) <= tail[1], 'splitter bar draw does not fit'
    toff = m.addr2off(tail[0])
    if any(data[toff:toff + len(tl)]):
        sys.exit('__TEXT padding at %08x is not empty' % tail[0])
    for at, code in ((free[0], head), (tail[0], tl)):
        data[m.addr2off(at):m.addr2off(at) + len(code)] = code
    struct.pack_into('>I', data, m.addr2off(end), 0x48000000 | ((free[0] - end) & 0x03fffffc))
    if not quiet:
        print('barupdate %08x file+%06x  %d bytes (browser window? its status bar), %d free' % (
            free[0], m.addr2off(free[0]), len(head), free[1] - free[0] - len(head)))
        print('barupdate %08x file+%06x  %d bytes (the bar draw), %d free' % (
            tail[0], m.addr2off(tail[0]), len(tl), tail[1] - tail[0] - len(tl)))
        print('barupdate %08x file+%06x  4e800020 -> b %08x  splitter DrawSelf: blr -> draw the bar too' % (
            end, m.addr2off(end), free[0]))


def place_view_loader(m, data, sites, quiet):
    """The View control loads VIEW_IMAGES images instead of 15: its last two
    load blocks become cave.build_view_loader's loop (ids 8613..8617), and
    the draw's first id per segment goes from VIEW_IDS to VIEW_IDS_NEW."""
    import cave
    last, landing, done = sites[VIEW_LOADER_LAST], sites[VIEW_LOADER_LANDING], sites[VIEW_LOADER_DONE]
    block = [w2(data, m, last + 4 * k) for k in range(29)]
    nxt = [w2(data, m, last + 0x74 + 4 * k) for k in range(28)]
    first = VIEW_IDS[0] + 13
    assert block[3] == 0x38800000 | first and nxt[3] == 0x38800000 | (first + 1), 'unexpected View loader blocks'
    assert [mask(w) for i, w in enumerate(block[:28]) if i != 3] == [mask(w) for i, w in enumerate(nxt) if i != 3]
    assert last + 0x74 + 4 * 28 == landing and landing + 0x1c == done, 'View loader has a different layout'
    code = cave.build_view_loader(last, block, last, VIEW_IDS[0] + VIEW_IMAGES, done, landing)
    room = landing - last
    assert len(code) <= room, 'View loader loop does not fit its two blocks'
    used = len(code)
    code += struct.pack('>I', NOP) * ((room - used) // 4)
    data[m.addr2off(last):m.addr2off(landing)] = code
    hi, lo = w2(data, m, VIEW_DRAW_IDS - 8), w2(data, m, VIEW_DRAW_IDS)
    assert hi >> 16 == 0x3d20 and lo >> 16 == 0x3929, 'expected lis/addi r9 before the View draw ids'
    ids = ((hi & 0xffff) << 16) + struct.unpack('>h', struct.pack('>H', lo & 0xffff))[0]
    off = m.addr2off(ids)
    assert struct.unpack_from('>3H', data, off) == VIEW_IDS, 'unexpected View draw ids'
    struct.pack_into('>3H', data, off, *VIEW_IDS_NEW)
    if not quiet:
        print('toolbar   %08x file+%06x  %d bytes: View loader blocks 14-15 -> loop over ids %d..%d, %d free' % (
            last, m.addr2off(last), used, first, VIEW_IDS[0] + VIEW_IMAGES - 1, room - used))
        print('toolbar   %08x file+%06x  View draw first ids %s -> %s' % (ids, off, VIEW_IDS, VIEW_IDS_NEW))


def bl_target_any(data, m, a):
    w = w2(data, m, a)
    assert w >> 26 == 18, 'expected a branch at %08x' % a
    disp = w & 0x03fffffc
    if disp & 0x02000000: disp -= 0x04000000
    return a + disp


def build_topbar_fix(m, data, sites):
    """cave.build_cgrect_port for this build: (code, entries, patches), where
    patches are (addr, expected word, new word, comment). Written by
    write_topbar_fix after the PATCHES loop ('slimbar' edits two words of
    the dead branch it reuses)."""
    import cave
    start, end = sites[BOTTOMBAR_DEAD[0]], sites[BOTTOMBAR_DEAD[0]] + (BOTTOMBAR_DEAD[1] - BOTTOMBAR_DEAD[0])
    fn = sites[CGRECT_STWU] - (CGRECT_STWU - CGRECT_FN)
    assert w2(data, m, fn) == 0x7c0802a6 and w2(data, m, fn + 4) == 0xbf81fff0, 'unexpected converter prologue'
    stubs = {nm: stub_addr(m, nm) for nm in cave.CGRECT_STUBS}
    code, at = cave.build_cgrect_port(start, fn, stubs)
    assert start + len(code) <= end, 'origin fix does not fit the dead branch'
    def b(src, dst, link=0): return 0x48000000 | ((dst - src) & 0x03fffffc) | link
    patches = [(sites[CGRECT_STWU], 0x9421ffa0, b(sites[CGRECT_STWU], at['normal']), 'QD->CG rect: prologue -> normal entry (r31 = 0)'),
               (sites[CGRECT_TOP], 0xa8010048, b(sites[CGRECT_TOP], at['top']), 'QD->CG rect: content top -> + port origin for port rects')]
    for c in CGRECT_PORT_CALLERS:
        a = sites[c]
        patches.append((a, None, b(a, at['port'], 1), 'QD->CG rect call -> port-rect entry'))
    return code, at, patches


def write_topbar_fix(m, data, fix, quiet):
    code, at, patches = fix
    off = m.addr2off(at['port'])
    data[off:off + len(code)] = code
    if not quiet:
        print('topbar    %08x file+%06x  %d bytes: QD->CG rect entry for port rects, in the dead bottom-bar branch' % (
            at['port'], off, len(code)))
    for a, expect, new, why in patches:
        cur = w2(data, m, a)
        if expect is None:
            assert cur >> 26 == 18 and cur & 1, 'expected a bl at %08x' % a
        else:
            assert cur == expect, '%08x: %08x != %08x (%s)' % (a, cur, expect, why)
        struct.pack_into('>I', data, m.addr2off(a), new)
        if not quiet:
            print('topbar    %08x file+%06x  %08x -> %08x  %s' % (a, m.addr2off(a), cur, new, why))


# --- 'stripes': a pinstriped sidebar (Panther 10.3.9; see cave.py).
#  - The sidebar and its items fill their background with SidebarStripes
#    (cave.build_sidebar_stripes): the view's draw, an item redrawn alone,
#    and an item being dragged. The routine lives in the fake background
#    control's draw (a metal leftover that draws nothing visible here).
#  - The divider is 7 px (6 columns of stripes, erased with the toolbar
#    brush, plus a 1 px line): its image (grip.py) is see-through with a
#    soft shadow and the arrow, as wide as the frame, and centered on the
#    divider's height (cave.build_centered_draw).
#  - No margin around the panes: the splitter insets both panes by 1 px when
#    its flag at +0xdc is set, which left a white row under the status bar's
#    line and a white column at the window's left edge (nothing repainted
#    it). Every reader of the flag reads it as 0; the top bar's bottom row
#    (-1) and the content width (+1), which pushed the panes' borders out of
#    the window, go back to 0; the divider is clipped to its full height.
#  - Scrolling: TSidebarView's ScrollBits (vtable slot 0x198) refreshes the
#    whole view instead of copying its pixels (the copied stripes moved with
#    the items). The slot is an external pointer: its relocation moves to
#    another slot bound to LView::ScrollBits, so neither dyld nor
#    update_prebinding writes it back. Those two edits are outside __TEXT
#    (stripes_outside_text gives them to mkinstaller.py).
STRIPES_WIDTH = 7
STRIPES_WIDTH_SITES = [0x4816c, 0x48198, 0x48388, 0x48a8c, 0x48ab0, 0x48c34, 0x48cdc, 0x4839c, 0x48c1c]
STRIPES_OVERRIDES = {   # (set, 10.3.9 address) -> (word, comment)
    ('slimbar', 0x48974): (0x7c840734, 'window layout: content width as is (stripes: no pane border to push out)'),
    ('topbar', 0x48958): (0x38000000, 'window layout: bottom bar height 14 -> 0 (stripes: no pane border)'),
    ('gap', 0x22534): (NOP, "grip draw: clip to the divider's full height (stripes)"),
    ('gap', 0x22538): (NOP, "grip draw: clip to the divider's full height (stripes)"),
}
SIDEBAR_FILL = (0x164a8, 0x164d4)      # sub_16444, the sidebar view's background fill
ITEM_FILL = (0x10064, 0x10090)         # sub_ffa4, an item redrawn alone (unless flags & 8)
DRAG_FILL = (0x18f7c4, 0x18f7f4)       # sub_18f784, an item while one is dragged
FAKEBG = (0x1af134, 0x1af218)          # TSidebarFakeBackgroundControl's draw (vtable slot 0x88)
RET1 = 0x450b4                         # an existing `li r3,1 ; blr`
MARGIN_FLAG_SITES = [0x48104, 0x48364, 0x48a3c, 0x48c14,   # li rX,1 after reading +0xdc -> li rX,0
                     0x2b7c0]          # (sub_2b76c: the new sidebar width = divider left - 2 * margin)
MARGIN_BRANCH = 0x485bc                # beq (no flag) -> b
CENTER_DRAW = (0x22518, 0x22550)       # the divider draw's x centering ... the clip's lswi
SCROLLBITS_SLOT, REFRESH_SLOT = 0x198, 0xcc
SCROLLBITS_THUNK = 0x29fff0            # the last 16 bytes of __TEXT
SIDEBAR_VIEW_CLASS = b'12TSidebarView'


def stripes_patches(patches):
    """PATCHES as 'stripes' changes them: the divider's width, and STRIPES_OVERRIDES."""
    out = []
    for name, addr, expect, action, why in patches:
        if name == 'gap' and addr in STRIPES_WIDTH_SITES:
            lo = action & 0xffff
            assert lo in (13, 0x10000 - 13), hex(action)
            action = (action & 0xffff0000) | ((STRIPES_WIDTH if lo == 13 else -STRIPES_WIDTH) & 0xffff)
            why = why.replace('13', str(STRIPES_WIDTH)) + ' (stripes)'
        elif (name, addr) in STRIPES_OVERRIDES:
            action, why = STRIPES_OVERRIDES[(name, addr)]
        out.append((name, addr, expect, action, why))
    return out


def scrollbits_relocation(m, data):
    """(the sidebar view's ScrollBits slot, its external relocation's file
    offset, another slot bound to LView::ScrollBits)."""
    vt = vtables_of(m, SIDEBAR_VIEW_CLASS)
    assert len(vt) == 1, 'TSidebarView vtable: %d found' % len(vt)
    slot = vt[0] + SCROLLBITS_SLOT
    extreloff, nextrel = m.dysymtab[14], m.dysymtab[15]
    mine = other = None
    for i in range(nextrel):
        a, info = struct.unpack_from('>II', data, extreloff + 8 * i)
        name = m.syms[info >> 8][0]
        if a == slot:
            assert name == '__ZN5LView10ScrollBitsEll', name
            mine = extreloff + 8 * i
        elif name == '__ZN5LView10ScrollBitsEll' and other is None:
            other = a
        if a == vt[0] + REFRESH_SLOT:
            assert name == '__ZN5LView7RefreshEv', name
    assert mine is not None and other is not None, 'ScrollBits relocation not found'
    return slot, mine, other


def stripes_outside_text(m):
    """The two edits 'stripes' makes outside __TEXT, as (file offset, length):
    the sidebar view's ScrollBits slot (__DATA) and its relocation's r_address.
    Tiger's 'stripes' edits are all in __TEXT: none."""
    if is_tiger(m):
        return []
    slot, rel, other = scrollbits_relocation(m, m.data)
    return [(m.addr2off(slot), 4), (rel, 4)]


def place_stripes(m, data, quiet):
    import cave
    w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
    put = lambda a, word: struct.pack_into('>I', data, m.addr2off(a), word)
    def write(a, code):
        data[m.addr2off(a):m.addr2off(a) + len(code)] = code
    set_fill, fill_rect = stub_addr(m, '_CGContextSetRGBFillColor'), stub_addr(m, '_CGContextFillRect')
    # the three white fills: SetRGBFillColor at +0x14 (+0x18), FillRect at +0x28 (+0x2c)
    for (a, end), at in ((SIDEBAR_FILL, 0x14), (ITEM_FILL, 0x14), (DRAG_FILL, 0x18)):
        assert bl_target(data, m, a + at) == set_fill and bl_target(data, m, a + at + 0x14) == fill_rect, \
            'stripes: no sidebar fill at %x (10.3.9 only)' % a
    assert w(SIDEBAR_FILL[0]) == 0x7f23cb78 and w(ITEM_FILL[0] - 0x14) == 0x389e0198 and w(DRAG_FILL[0] - 0x18) == 0x38830198
    assert w(FAKEBG[0]) == 0x7c0802a6 and w(FAKEBG[1] - 4) == 0x4e800020 and w(FAKEBG[1] - 0x18) == 0x80010088
    assert struct.unpack_from('>II', data, m.addr2off(RET1)) == (0x38600001, 0x4e800020)
    stubs = {nm: stub_addr(m, nm) for nm in cave.SIDEBAR_STRIPES_STUBS}
    table = struct.pack('>4f', *[g / 255 for g in cave.STRIPE_GRAYS]) + struct.pack('>f', 1.0)
    # the view's fill, with the gray table after it (SidebarStripes' address is known first)
    probe, where = cave.build_stripes_call(SIDEBAR_FILL[0], SIDEBAR_FILL[1], 25, 31, FAKEBG[0], copy_reg=27, table=table)
    code, entry = cave.build_sidebar_stripes(FAKEBG[0], RET1, where, stubs)
    assert len(code) <= FAKEBG[1] - FAKEBG[0], 'SidebarStripes does not fit the fake background draw'
    write(FAKEBG[0], code + struct.pack('>I', NOP) * ((FAKEBG[1] - FAKEBG[0] - len(code)) // 4))
    write(SIDEBAR_FILL[0], cave.build_stripes_call(SIDEBAR_FILL[0], SIDEBAR_FILL[1], 25, 31, entry, copy_reg=27, table=table)[0])
    write(ITEM_FILL[0], cave.build_stripes_call(ITEM_FILL[0], ITEM_FILL[1], 27, 28, entry, copy_reg=29)[0])
    write(DRAG_FILL[0], cave.build_stripes_call(DRAG_FILL[0], DRAG_FILL[1], 26, 30, entry, copy_reg=31,
                                                setup=[cave.d_form(14, 31, 1, 0x50)])[0])   # addi r31,r1,0x50
    place_no_margin(m, data)
    # scrolling: ScrollBits -> Refresh
    slot, rel, other = scrollbits_relocation(m, data)
    o = m.addr2off(SCROLLBITS_THUNK)
    assert not any(data[o:o + 16]), 'end of __TEXT in use'
    write(SCROLLBITS_THUNK, cave.build_refresh_thunk(SCROLLBITS_THUNK, REFRESH_SLOT))
    put(slot, SCROLLBITS_THUNK)
    struct.pack_into('>I', data, rel, other)
    if not quiet:
        print('stripes   %08x file+%06x  %d bytes (SidebarStripes) in the fake background draw' % (
            FAKEBG[0], m.addr2off(FAKEBG[0]), len(code)))
        print('stripes   fills %s -> SidebarStripes; pane margin -> 0; divider image centered' % (
            ', '.join('%x' % a for a, _ in (SIDEBAR_FILL, ITEM_FILL, DRAG_FILL))))
        print('stripes   ScrollBits slot %x -> %x (Refresh), relocation moved to %x' % (slot, SCROLLBITS_THUNK, other))


def place_no_margin(m, data, margin=0):
    """The sidebar styles' layout (see 'stripes' above): no pane margin (or
    `margin` px, 'well'), the divider image centered on the divider's height."""
    import cave
    w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
    put = lambda a, word: struct.pack_into('>I', data, m.addr2off(a), word)
    def write(a, code):
        data[m.addr2off(a):m.addr2off(a) + len(code)] = code
    # the pane margin
    for a in MARGIN_FLAG_SITES:
        assert w(a) >> 26 == 14 and (w(a) >> 16) & 31 == 0 and w(a) & 0xffff == 1, 'margin flag site %x' % a
        assert any(w(a - 4 * k) >> 26 == 32 and w(a - 4 * k) & 0xffff == 0xdc for k in range(1, 12)), 'margin flag %x' % a
        put(a, (w(a) & 0xffff0000) | margin)
    assert w(MARGIN_BRANCH) == 0x41be0108 and w(MARGIN_BRANCH - 8) & 0xffff == 0xdc
    if not margin:                     # (with one, its invalidation stays)
        put(MARGIN_BRANCH, 0x48000108)
    # the divider image centered on the divider's height
    a, end = CENTER_DRAW
    assert [w(a + 4 * k) for k in (0, 1, 2, 4, 6, 9)] == [0xed8a0032, 0xc1a10078, 0xed690032, 0x80610044, 0xc181007c, 0xc1610070]
    assert w(end) == 0x7c9d84aa and w(end + 12) == 0x7c9d84aa, 'divider clip/draw rects'
    assert w(0x22498) == 0xcbe2cab8 and w(0x22514) == 0xc121005c, 'f31 = 2^52, f9 = image height'
    write(a, cave.build_centered_draw(a, end))
    put(end, (31 << 26) | (4 << 21) | (28 << 16) | (16 << 11) | (597 << 1))   # lswi r4,r28,16: the clip's copy


# --- 'header': the sidebar under an Aqua list header (Panther 10.3.9; see
# cave.build_sidebar_header and tools/header.py). On 'stripes'' layout:
#  - The divider (7 px) is erased white, its image a 1 px line by the files
#    (grip.py header_divider_png): the sidebar looks 6 px wider, with a line.
#  - The sidebar starts HEADER_ROWS - 1 lower (the header's first row is the
#    status bar's last, EDGE_PATCHES) and is as much shorter: placed so when
#    the window is laid out, and its height, then and on every resize, the
#    splitter's - those rows. (Dragging the divider changes only its width.)
#    The file pane's column header is in line with ours.
#  - The splitter's DrawSelf draws the header in those rows (the first of its
#    pane outline calls, nops since 'gap', calls SidebarHeader): the active
#    or the inactive window's (its label gray). SidebarHeader lives in the
#    pane outline routine itself (dead since 'gap') and the fake background
#    draw (unused here: no stripes); its statics in __DATA's zero-fill tail,
#    past __common.
HEADER_ROWS = 17
_HD = HEADER_ROWS - 1                  # the header's first row is the status bar's last (EDGE_*)
# The top edge of 'header' and 'well' (cave.EDGE_*): the status bar leaves its
# last row to the splitter, which draws it in the DrawSelf call below (also
# with the sidebar collapsed); the file pane starts a row higher, under it,
# so its own first row is hidden (the list header's line, the icon view's
# white) and scrolls with nothing of ours in it.
EDGE_PATCHES = [     # (10.3.9 address, word before (with 'stripes'' layout), new word, comment)
    (0x4815c, 0x7fc5f378, 0x38a0ffff, 'layout: file pane y = margin -> -1 (under the top edge)'),
    (0x48194, 0x7cbd2850, 0x38a50001, 'layout: file pane height = H - 2m -> H + 1'),
    (0x48c44, 0x7fc5f378, 0x38a0ffff, 'file pane: y = margin -> -1 (under the top edge)'),
    (0x48c64, 0x7ca02850, 0x38a50001, 'file pane: height = H - 2m -> H + 1'),
    (0x22574, 0x409e0014, NOP, 'DrawSelf: skip the first outline call when collapsed -> always (the top edge)'),
]
HEADER_PATCHES = EDGE_PATCHES + [   # (10.3.9 address, expected word, new word, comment)
    (0x48110, 0x7fc5f378, 0x38be0000 | _HD, 'layout: sidebar y = margin -> margin + header rows - 1 (addi r5,r30,16)'),
    (0x48138, 0x7ca50734, 0x38a50000 | (-_HD & 0xffff), 'layout: sidebar height -= header rows - 1 (addi r5,r5,-16)'),
    (0x48a98, 0x7c090050, 0x30000000 | (-_HD & 0xffff), 'resize: sidebar height = splitter - header rows + 1 (addic r0,r0,-16; margin 0)'),
]
HEADER_CALL = 0x22584                  # DrawSelf: bl <outline the sidebar> ('gap': nop), r3 = splitter, r4 = ctx
HEADER_LOADER = 0x2227c                # sub_2227c(&holder, handle): CGImage from a 'PNG ' handle (the grip's loader)
HEADER_STATICS = 0x325de0              # 16 bytes past __common (0x3257d0 + 0x608), in __DATA's vm size
OUTLINE_FN = (0x20788, 0x2081c)        # sub_20788, a pane's outline: called only from DrawSelf's two nopped calls


def data_tail_free(m, addr, n):
    """True if [addr, addr + n) lies past every __DATA section, inside the
    segment's vm size (zero-filled memory nothing else uses)."""
    seg = [x for x in m.segments if x['name'] == '__DATA'][0]
    last = max(x['addr'] + x['size'] for x in m.sections if x['seg'] == '__DATA')
    return last <= addr and addr + n <= seg['vmaddr'] + seg['vmsize']


def place_header(m, data, fix, quiet):
    import cave, header
    w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
    put = lambda a, word: struct.pack_into('>I', data, m.addr2off(a), word)
    assert fix, "'header' needs 'topbar' (its port rect converter)"
    place_no_margin(m, data)
    for a, expect, new, why in HEADER_PATCHES:
        assert w(a) == expect, 'header: %08x is %08x, not %08x (%s)' % (a, w(a), expect, why)
        put(a, new)
        if not quiet:
            print('header    %08x file+%06x  %08x -> %08x  %s' % (a, m.addr2off(a), expect, new, why))
    assert w(HEADER_CALL) == NOP and w(HEADER_CALL - 12) == 0x7fe3fb78 and w(HEADER_CALL - 8) == 0x80810044, 'header call site'
    assert w(HEADER_LOADER) == 0x7c0802a6 and w(HEADER_LOADER + 0x60) >> 26 == 18, 'image loader'
    assert w(FAKEBG[0]) == 0x7c0802a6 and w(FAKEBG[1] - 4) == 0x4e800020, 'fake background draw'
    assert struct.unpack_from('>II', data, m.addr2off(RET1)) == (0x38600001, 0x4e800020)
    assert data_tail_free(m, HEADER_STATICS, 16), 'no room for the header statics'
    stubs = {nm: stub_addr(m, nm) for nm in cave.SIDEBAR_HEADER_STUBS}
    head, tail, rest = style_regions(m, data)
    pieces = cave.build_sidebar_header(head[0], tail[0], rest[0], HEADER_STATICS, HEADER_LOADER,
                                       bl_target(data, m, DIVIDER_FRAME_CALL), fix[1]['port'], stubs,
                                       header.HEADER_ID, HEADER_ROWS, header.HEADER_WIDTH)
    write_style_pieces(m, data, (head, tail, rest), pieces, 'SidebarHeader', quiet)
    put(HEADER_CALL, 0x48000001 | ((head[0] - HEADER_CALL) & 0x03fffffc))
    if not quiet:
        print('header    %08x file+%06x  DrawSelf: nop -> bl SidebarHeader; statics at %08x' % (
            HEADER_CALL, m.addr2off(HEADER_CALL), HEADER_STATICS))


def style_regions(m, data):
    """The three dead stretches the 'header' and 'well' routines live in, as
    (start, end): the pane outline routine (dead since 'gap'), the fake
    background draw after its `b RET1` (unused without 'stripes'), and the
    tail of the View loader's two blocks after 'toolbar''s loop."""
    w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
    head, end = OUTLINE_FN
    assert w(head) == 0x7c0802a6 and w(end - 4) == 0x4e800020 and w(end) == 0x7c0802a6, 'pane outline routine'
    assert w(HEADER_CALL + 16) == NOP, "the other outline call: 'gap''s nop"
    assert w(FAKEBG[0]) == 0x7c0802a6 and w(FAKEBG[1] - 4) == 0x4e800020, 'fake background draw'
    assert struct.unpack_from('>II', data, m.addr2off(RET1)) == (0x38600001, 0x4e800020)
    lo = VIEW_LOADER_LANDING
    assert w(lo - 4) == NOP, "'header' and 'well' need 'toolbar' (the View loader's free tail)"
    while w(lo - 4) == NOP:
        lo -= 4
    return (head, end), (FAKEBG[0] + 4, FAKEBG[1]), (lo, VIEW_LOADER_LANDING)


def write_style_pieces(m, data, regions, pieces, name, quiet):
    import cave
    for k, ((a, e), code) in enumerate(zip(regions, pieces)):
        assert len(code) <= e - a, '%s piece %d (%d bytes) does not fit %x..%x' % (name, k, len(code), a, e)
        blob = code + struct.pack('>I', NOP) * ((e - a - len(code)) // 4)
        if a == FAKEBG[0] + 4:             # the fake background draw draws nothing
            b = cave.Asm(FAKEBG[0]); b.b(RET1)
            blob = b.assemble() + blob
            a = FAKEBG[0]
        data[m.addr2off(a):m.addr2off(a) + len(blob)] = blob
        if not quiet:
            print('%-9s %08x file+%06x  %d bytes (%s, piece %d), %d free' % (
                name[:9].lower(), regions[k][0], m.addr2off(regions[k][0]), len(code), name, k + 1,
                regions[k][1] - regions[k][0] - len(code)))



# --- 'well': the sidebar as a white inset list on the window's pinstripes,
# framed like an Aqua list box (Panther 10.3.9; see cave.build_well_frame).
# The splitter's pane margin (its +0xdc flag's 1 px, which 'stripes' makes 0)
# is WELL_MARGIN for the sidebar: it sits that far in from the splitter's
# left, top and bottom edges. The divider, right after the sidebar's frame
# line, is WELL_MARGIN wide (its image: stripes, then the 1 px line), and the
# file pane starts right after it, with no margin, as with 'stripes':
#   sidebar   x = m, y = 0, width w, height H - m         (m = WELL_MARGIN)
#   divider   left = w + m + 1, right = left + m          (collapsed: 0, m)
#   files     x = w + 2m + 1 (collapsed: m), y = -1, the rest of the splitter
# (y 0 and -1: the frame's top line and the files' top edge are the status
# bar's last row, EDGE_PATCHES.)
# The layout's other readers of the margin follow: the widest sidebar, and
# the sidebar's width while the divider is dragged (left - m - 1). The ring
# of margin the layout invalidates around a pane grows to m.
WELL_MARGIN = 5
WELL_DRAWSELF_ERASE = 0x22420          # DrawSelf: bl DividerErase ('gap'), its return address + 4
_M = WELL_MARGIN
WELL_PATCHES = [   # (10.3.9 address, word before (with 'stripes'' layout), new word, comment)
    (0x48110, 0x7fc5f378, 0x38a00000, 'layout: sidebar y = m -> 0 (the frame top: the top edge)'),
    (0x48130, 0x7cbd2850, 0x7cbe2850, 'layout: sidebar height = H - 2m -> H - m'),
    (0x48a98, 0x7c090050, 0x7c1c0050, 'resize: sidebar height = H - 2m -> H - m'),
    (0x48154, 0x1c1e0003, 0x57c0083c, 'layout: file pane x = w + 3m + 7 -> w + 2m + 1 (mulli 3 -> slwi 1)'),
    (0x4816c, 0x38840007, 0x38840001, 'layout: file pane x: + 7 -> + 1'),
    (0x4817c, 0x57c2103a, 0x57c2083c, 'layout: file pane width = W - w - 4m - 7 -> - 2m - 1 (slwi 2 -> 1)'),
    (0x48198, 0x3884fff9, 0x3884ffff, 'layout: file pane width: - 7 -> - 1'),
    (0x48378, 0x5442083c, 0x38420001, 'divider: left = w + 2m -> w + m + 1'),
    (0x48388, 0x38420007, 0x38420000 | _M, 'divider: right = left + 7 -> + m'),
    (0x4839c, 0x38000007, 0x38000000 | _M, 'divider, sidebar collapsed: right = 7 -> m'),
    (0x48a8c, 0x38420007, 0x38420001, 'resize: room for the divider 7 -> 1 (+ 2m)'),
    (0x48ab0, 0x3842fff9, 0x3842ffff, 'resize: sidebar width - 7 -> - 1 (- 2m)'),
    (0x48c1c, 0x3bfe0007, 0x3bfe0000, 'file pane, sidebar collapsed: x = m + 7 -> m'),
    (0x48c2c, 0x1c1e0003, 0x57c0083c, 'file pane: x = w + 3m + 7 -> w + 2m + 1 (mulli 3 -> slwi 1)'),
    (0x48c34, 0x3be20007, 0x3be20001, 'file pane: x: + 7 -> + 1'),
    (0x48c68, 0x7c9e2050, NOP, 'file pane: width = W - x - m -> W - x'),
    (0x48cbc, 0x38400001, 0x38400000 | _M, 'widest sidebar: margin 1 -> m'),
    (0x48cdc, 0x3863fff9, 0x3863ffff, 'widest sidebar: W - d0 - 2m - 7 -> - 1'),
    (0x2b80c, 0x5760083c, 0x381b0001, 'divider drag: sidebar width = left - 2m -> left - m - 1'),
    (0x485cc, 0x38a0ffff, 0x38a00000 | (-_M & 0xffff), 'invalidate: the ring around a pane, 1 -> m px (v)'),
    (0x485d0, 0x3880ffff, 0x38800000 | (-_M & 0xffff), 'invalidate: the ring around a pane, 1 -> m px (h)'),
] + EDGE_PATCHES


def place_well(m, data, fix, quiet):
    import cave
    w = lambda a: struct.unpack_from('>I', data, m.addr2off(a))[0]
    put = lambda a, word: struct.pack_into('>I', data, m.addr2off(a), word)
    assert fix, "'well' needs 'topbar' (its port rect converter)"
    place_no_margin(m, data, WELL_MARGIN)
    for a, expect, new, why in WELL_PATCHES:
        assert w(a) == expect, 'well: %08x is %08x, not %08x (%s)' % (a, w(a), expect, why)
        put(a, new)
        if not quiet:
            print('well      %08x file+%06x  %08x -> %08x  %s' % (a, m.addr2off(a), expect, new, why))
    assert w(HEADER_CALL) == NOP and w(HEADER_CALL - 12) == 0x7fe3fb78 and w(HEADER_CALL - 8) == 0x80810044, 'frame call site'
    stubs = {nm: stub_addr(m, nm) for nm in cave.WELL_FRAME_STUBS}
    head, tail, rest = style_regions(m, data)
    pieces = cave.build_well_frame(head[0], tail[0], rest[0], bl_target(data, m, DIVIDER_FRAME_CALL), fix[1]['port'],
                                   stubs, WELL_MARGIN)
    write_style_pieces(m, data, (head, tail, rest), pieces, 'WellFrame', quiet)
    put(HEADER_CALL, 0x48000001 | ((head[0] - HEADER_CALL) & 0x03fffffc))
    if not quiet:
        print('well      %08x file+%06x  DrawSelf: nop -> bl WellFrame' % (HEADER_CALL, m.addr2off(HEADER_CALL)))

def apply(path_in, path_out, names=SET_NAMES, quiet=False):
    m = MachO(path_in)
    if is_tiger(m):
        return apply_tiger(m, path_out, names, quiet)
    ref = MachO(REF_PATH)
    sites = locate(ref, m, names)
    data = bytearray(m.data)
    cv = None
    if 'topbar' in names:
        assert 'shadow' in names and 'slimbar' in names, "'topbar' needs 'shadow' and 'slimbar'"
    if 'shadow' in names or 'softlines' in names:
        cv = place_cave(m, data, sites[0x23b90], quiet, keep_last_row=style_of(names) in ('header', 'well'))
    fix = build_topbar_fix(m, data, sites) if 'topbar' in names else None
    divider = None
    if 'gap' in names:
        assert 'statusbar' in names, "'gap' needs 'statusbar' (its helper lives in the dead metal branch)"
        divider = place_divider_erase(m, data, sites, quiet, style=style_of(names))
        free = place_divider(m, data, sites, quiet, cg_entry=fix[1]['port'] if fix else None)
    if 'barupdate' in names:
        assert 'gap' in names, "'barupdate' needs 'gap' (it lives after the splitter bar draw)"
        assert cv, "'barupdate' needs 'shadow' (its tail follows the bar routine)"
        place_barupdate(m, data, sites, free, cv['free'], quiet)
    if 'toolbar' in names:
        place_view_loader(m, data, sites, quiet)
    style = style_of(names)
    if style:
        assert all(n in names for n in ('gap', 'topbar', 'slimbar', 'statusbar')), "'%s' needs 'gap' and 'topbar'" % style
        assert all(sites[a] == a for a in STRIPES_WIDTH_SITES), "'%s' is for Finder 10.3.9 only" % style
    for p in (stripes_patches(PATCHES) if style else PATCHES):
        name, refaddr, expect, action, why = p
        if name not in names:
            continue
        addr = sites[refaddr]
        off = m.addr2off(addr)
        cur = struct.unpack_from('>I', data, off)[0]
        if expect is not None and mask(cur) != mask(expect):
            sys.exit('mismatch at %08x: %08x != expected %08x (%s)' % (addr, cur, expect, why))
        if isinstance(action, int):
            new = action
        elif action[0] == 'bl_new':     # a new call in place of any instruction
            new = 0x48000001 | ((stub_addr(m, action[1]) - addr) & 0x03fffffc)
        elif action[0] == 'bl':
            assert cur >> 26 == 18 and cur & 1, 'expected a bl at %08x' % addr
            new = 0x48000001 | ((stub_addr(m, action[1]) - addr) & 0x03fffffc)
        elif action[0] == 'bl_divider':
            assert cur >> 26 == 18 and cur & 1, 'expected a bl at %08x' % addr
            new = 0x48000001 | ((divider - addr) & 0x03fffffc)
        elif action[0] == 'cave':
            new = 0x48000000 | ((cv['addr'] - addr) & 0x03fffffc)
        elif action[0] == 'lfs_gray':
            # lfs f1,lo(0.6)(rB) after lis rB,hi -> load the lighter gray from the cave
            base = None
            for j in range(1, 6):
                pw = struct.unpack_from('>I', data, off - 4*j)[0]
                if pw >> 26 == 15 and (pw >> 16) & 31 == 0 and (pw >> 21) & 31 == (cur >> 16) & 31:
                    base = (pw & 0xffff) << 16
                    break
            assert base is not None, 'no lis base before lfs at %08x' % addr
            disp = cv[action[1]] - base
            assert -0x8000 <= disp < 0x8000
            new = (cur & 0xffff0000) | (disp & 0xffff)
        elif action[0] == 'always':
            assert cur >> 26 == 16, 'expected a bc at %08x' % addr
            disp = cur & 0xfffc
            if disp & 0x8000: disp -= 0x10000
            new = 0x48000000 | (disp & 0x03fffffc)
        struct.pack_into('>I', data, off, new)
        if not quiet:
            print('%-9s %08x file+%06x  %08x -> %08x  %s' % (name, addr, off, cur, new, why))
    if fix:
        write_topbar_fix(m, data, fix, quiet)
    if style == 'stripes':
        place_stripes(m, data, quiet)
    elif style == 'header':
        place_header(m, data, fix, quiet)
    elif style == 'well':
        place_well(m, data, fix, quiet)
    open(path_out, 'wb').write(bytes(data))
    return sites


if __name__ == '__main__':
    names = sys.argv[3].split(',') if len(sys.argv) > 3 else SET_NAMES
    apply(sys.argv[1], sys.argv[2], names)
