/* Read only focus metadata; never reads account/password contents.
 * Build: zig cc -target x86_64-windows-gnu -Os -s focused-edit.c -o focused-edit.exe -luser32
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    SetProcessDPIAware();
    GUITHREADINFO g = {0};
    g.cbSize = sizeof(g);
    if (!GetGUIThreadInfo(0, &g) || !g.hwndFocus) { puts("null"); return 0; }
    char cls[128] = {0};
    GetClassNameA(g.hwndFocus, cls, sizeof(cls));
    if (_strnicmp(cls, "Edit", 4) && _strnicmp(cls, "RichEdit", 8)) { puts("null"); return 0; }
    if (!IsWindowVisible(g.hwndFocus) || !IsWindowEnabled(g.hwndFocus) ||
        (GetWindowLongPtr(g.hwndFocus, GWL_STYLE) & ES_READONLY)) { puts("null"); return 0; }
    HWND root = GetAncestor(g.hwndFocus, GA_ROOT);
    RECT r, client;
    GetWindowRect(g.hwndFocus, &r);
    /* MPAY draws a tall input row around a much shorter child EditWnd.
     * The row padding also gives this edit focus on click. Check that row,
     * otherwise account/phone clicks below the text baseline are rejected.
     */
    char root_class[128] = {0};
    GetClassNameA(root, root_class, sizeof(root_class));
    if (!strcmp(root_class, "MPAY_LOGIN") && !_strnicmp(cls, "EditWnd_", 8)) {
        LONG pad = (r.bottom - r.top) * 2 / 3;
        InflateRect(&r, pad, pad);
    }
    POINT mouse; GetCursorPos(&mouse);
    if (!PtInRect(&r, mouse)) { puts("null"); return 0; }
    GetClientRect(root, &client);
    POINT origin = {0, 0};
    ClientToScreen(root, &origin);
    printf("{\"x\":%ld,\"y\":%ld,\"w\":%ld,\"h\":%ld,\"window_w\":%ld,\"window_h\":%ld,\"mode\":%d}\n",
        r.left-origin.x, r.top-origin.y, r.right-r.left, r.bottom-r.top,
        client.right, client.bottom,
        (GetWindowLongPtr(g.hwndFocus, GWL_STYLE) & ES_NUMBER) ? 3 : 0);
    return 0;
}
