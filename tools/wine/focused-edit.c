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
