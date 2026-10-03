/* Prepare focused text input; never reads account/password contents.
 * Build: zig cc -target x86_64-windows-gnu -Os -s focused-edit.c -o focused-edit.exe -luser32
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static DWORD login_pid;
static BOOL CALLBACK suspend_age(HWND h, LPARAM ignored) {
    DWORD pid = 0;
    GetWindowThreadProcessId(h, &pid);
    if (pid != login_pid) return TRUE;
    char cls[128] = {0};
    GetClassNameA(h, cls, sizeof(cls));
    if (strcmp(cls, "MPAY_AGE_TIPS")) return TRUE;
    /* This is the informational age card, not the verification/consent dialog.
     * Keep it from reactivating when Steam opens its floating keyboard.
     */
    SetWindowLongPtr(h, GWL_EXSTYLE,
        GetWindowLongPtr(h, GWL_EXSTYLE) | WS_EX_NOACTIVATE);
    ShowWindow(h, SW_HIDE);
    return TRUE;
}

static void keep_edit_focus(HWND root, HWND edit) {
    DWORD target = GetWindowThreadProcessId(root, NULL);
    DWORD current = GetCurrentThreadId();
    if (current != target && !AttachThreadInput(current, target, TRUE)) return;
    SetFocus(edit);
    if (current != target) AttachThreadInput(current, target, FALSE);
}

static void guard_edit(HWND root, HWND edit) {
    DWORD pid = 0, edit_pid = 0;
    DWORD tid = GetWindowThreadProcessId(root, &pid);
    GetWindowThreadProcessId(edit, &edit_pid);
    if (!pid || pid != edit_pid || !IsChild(root, edit)) return;
    char cls[128] = {0};
    GetClassNameA(root, cls, sizeof(cls));
    if (strcmp(cls, "MPAY_LOGIN")) return;
    login_pid = pid;
    /* Keep the child edit, not just its X11 top-level, through the opening animation. */
    for (int i = 0; i < 40 && IsWindow(edit) && IsWindowEnabled(root); ++i) {
        GUITHREADINFO info = {0}; info.cbSize = sizeof(info);
        if (GetGUIThreadInfo(tid, &info) && info.hwndFocus != edit) {
            char focused_class[128] = {0};
            GetClassNameA(info.hwndFocus, focused_class, sizeof(focused_class));
            /* Respect an intentional move to another editable field. */
            if (!_strnicmp(focused_class, "Edit", 4) || !_strnicmp(focused_class, "RichEdit", 8)) break;
            EnumWindows(suspend_age, 0);
            keep_edit_focus(root, edit);
        }
        Sleep(50);
    }
}

static void start_guard(HWND root, HWND edit) {
    wchar_t exe[MAX_PATH], cmd[MAX_PATH + 128];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    _snwprintf(cmd, MAX_PATH + 128, L"\"%ls\" --keep-edit %llu %llu", exe,
        (unsigned long long)(ULONG_PTR)root, (unsigned long long)(ULONG_PTR)edit);
    STARTUPINFOW si = {0}; si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {0};
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    }
}

int main(int argc, char **argv) {
    SetProcessDPIAware();
    if (argc == 4 && !strcmp(argv[1], "--keep-edit")) {
        guard_edit((HWND)(ULONG_PTR)strtoull(argv[2], NULL, 10),
                   (HWND)(ULONG_PTR)strtoull(argv[3], NULL, 10));
        return 0;
    }
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
    if (!strcmp(root_class, "MPAY_LOGIN")) {
        GetWindowThreadProcessId(root, &login_pid);
        EnumWindows(suspend_age, 0);
        keep_edit_focus(root, g.hwndFocus);
        start_guard(root, g.hwndFocus);
    }
    GetClientRect(root, &client);
    POINT origin = {0, 0};
    ClientToScreen(root, &origin);
    printf("{\"x\":%ld,\"y\":%ld,\"w\":%ld,\"h\":%ld,\"window_w\":%ld,\"window_h\":%ld,\"mode\":%d}\n",
        r.left-origin.x, r.top-origin.y, r.right-r.left, r.bottom-r.top,
        client.right, client.bottom,
        (GetWindowLongPtr(g.hwndFocus, GWL_STYLE) & ES_NUMBER) ? 3 : 0);
    return 0;
}
