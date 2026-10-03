/* Prepare focused text input; never reads account/password contents.
 * Build: zig cc -target x86_64-windows-gnu -Os -s focused-edit.c -o focused-edit.exe -luser32
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static DWORD login_pid;

static void hide_auxiliary(HWND h) {
    /* Unmapping alone leaves a live Wine window that the SDK can show again.
     * Disable first to remove it from focus selection, then close on its own
     * GUI thread. Never use DestroyWindow across process boundaries. */
    EnableWindow(h, FALSE);
    SetWindowLongPtr(h, GWL_EXSTYLE,
        GetWindowLongPtr(h, GWL_EXSTYLE) | WS_EX_NOACTIVATE);
    ShowWindow(h, SW_HIDE);
}

static void close_auxiliary(HWND h) {
    hide_auxiliary(h);
    DWORD_PTR result;
    SendMessageTimeoutW(h, WM_CLOSE, 0, 0, SMTO_ABORTIFHUNG | SMTO_BLOCK, 100, &result);
}

static BOOL CALLBACK hide_class(HWND h, LPARAM wanted) {
    char cls[128] = {0};
    GetClassNameA(h, cls, sizeof(cls));
    if (!strcmp(cls, (const char *)wanted)) hide_auxiliary(h);
    return TRUE;
}

static BOOL CALLBACK suppress_class(HWND h, LPARAM wanted) {
    char cls[128] = {0};
    GetClassNameA(h, cls, sizeof(cls));
    if (!strcmp(cls, (const char *)wanted)) close_auxiliary(h);
    return TRUE;
}
static BOOL CALLBACK suspend_age(HWND h, LPARAM ignored) {
    DWORD pid = 0;
    GetWindowThreadProcessId(h, &pid);
    if (pid != login_pid) return TRUE;
    char cls[128] = {0};
    GetClassNameA(h, cls, sizeof(cls));
    if (strcmp(cls, "MPAY_AGE_TIPS")) return TRUE;
    /* Exact informational age-card class; never the consent/verification UI. */
    close_auxiliary(h);
    return TRUE;
}

static void keep_edit_focus(HWND root, HWND edit) {
    DWORD target = GetWindowThreadProcessId(root, NULL);
    DWORD current = GetCurrentThreadId();
    if (current != target && !AttachThreadInput(current, target, TRUE)) return;
    SetFocus(edit);
    if (current != target) AttachThreadInput(current, target, FALSE);
}

static HWND restore_edit(HWND root, DWORD tid, int x, int y) {
    DWORD_PTR result;
    /* MPAY destroys its transient EditWnd on blur. Re-enter only the recorded
     * input row using window-local messages; do not move/click the Steam pointer.
     * MPAY hit testing expects physical client coordinates, even though its
     * window reports an unaware DPI context. */
    LPARAM pos = MAKELPARAM(x, y);
    if (!SendMessageTimeoutW(root, WM_LBUTTONDOWN, MK_LBUTTON, pos,
                            SMTO_ABORTIFHUNG | SMTO_BLOCK, 100, &result)) return NULL;
    SendMessageTimeoutW(root, WM_LBUTTONUP, 0, pos,
                       SMTO_ABORTIFHUNG | SMTO_BLOCK, 100, &result);
    GUITHREADINFO g = {0}; g.cbSize = sizeof(g);
    if (!GetGUIThreadInfo(tid, &g) || !IsChild(root, g.hwndFocus)) return NULL;
    char cls[128] = {0}; GetClassNameA(g.hwndFocus, cls, sizeof(cls));
    if (_strnicmp(cls, "Edit", 4) && _strnicmp(cls, "RichEdit", 8)) return NULL;
    return g.hwndFocus;
}

static void guard_edit(HWND root, HWND edit, int x, int y) {
    DWORD pid = 0, edit_pid = 0;
    DWORD tid = GetWindowThreadProcessId(root, &pid);
    GetWindowThreadProcessId(edit, &edit_pid);
    if (!pid || (IsWindow(edit) && (pid != edit_pid || !IsChild(root, edit)))) return;
    char cls[128] = {0};
    GetClassNameA(root, cls, sizeof(cls));
    if (strcmp(cls, "MPAY_LOGIN")) return;
    login_pid = pid;
    /* Keep the child edit, not just its X11 top-level, through the opening animation. */
    ULONGLONG deadline = GetTickCount64() + 1800;
    while (GetTickCount64() < deadline && IsWindow(root) && IsWindowEnabled(root)) {
        GUITHREADINFO info = {0}; info.cbSize = sizeof(info);
        if (GetGUIThreadInfo(tid, &info) && info.hwndFocus != edit) {
            char focused_class[128] = {0};
            GetClassNameA(info.hwndFocus, focused_class, sizeof(focused_class));
            /* Respect an intentional move to another editable field. */
            if (!_strnicmp(focused_class, "Edit", 4) || !_strnicmp(focused_class, "RichEdit", 8)) break;
            /* Do not steal focus from a real verification/consent dialog. */
            if (info.hwndFocus && info.hwndFocus != root &&
                GetAncestor(info.hwndFocus, GA_ROOT) != root &&
                strcmp(focused_class, "MPAY_AGE_TIPS")) break;
            EnumWindows(suspend_age, 0);
            if (!IsWindow(edit)) {
                edit = restore_edit(root, tid, x, y);
                if (!edit) { Sleep(100); continue; }
            }
            keep_edit_focus(root, edit);
        }
        Sleep(50);
    }
}

static void start_guard(HWND root, HWND edit) {
    RECT r; GetWindowRect(edit, &r);
    POINT point = {(r.left + r.right) / 2, (r.top + r.bottom) / 2};
    ScreenToClient(root, &point);
    wchar_t exe[MAX_PATH], cmd[MAX_PATH + 128];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    _snwprintf(cmd, MAX_PATH + 128, L"\"%ls\" --keep-edit %llu %llu %ld %ld", exe,
        (unsigned long long)(ULONG_PTR)root, (unsigned long long)(ULONG_PTR)edit, point.x, point.y);
    STARTUPINFOW si = {0}; si.cb = sizeof(si);
    SECURITY_ATTRIBUTES sa = {sizeof(sa), NULL, TRUE};
    HANDLE nul = CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, NULL);
    if (nul == INVALID_HANDLE_VALUE) return;
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = si.hStdOutput = si.hStdError = nul;
    PROCESS_INFORMATION pi = {0};
    if (CreateProcessW(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    }
    CloseHandle(nul);
}

int main(int argc, char **argv) {
    SetProcessDPIAware();
    if (argc == 3 && (!strcmp(argv[1], "--suppress-window") || !strcmp(argv[1], "--hide-window"))) {
        if (!argv[2][0]) return 1;
        for (;;) {
            EnumWindows(!strcmp(argv[1], "--hide-window") ? hide_class : suppress_class, (LPARAM)argv[2]);
            Sleep(25);
        }
    }
    if (argc == 6 && !strcmp(argv[1], "--keep-edit")) {
        guard_edit((HWND)(ULONG_PTR)strtoull(argv[2], NULL, 10),
                   (HWND)(ULONG_PTR)strtoull(argv[3], NULL, 10), atoi(argv[4]), atoi(argv[5]));
        return 0;
    }
    GUITHREADINFO g = {0};
    g.cbSize = sizeof(g);
    if (!GetGUIThreadInfo(0, &g) || !g.hwndFocus) { puts("null"); return 0; }
    BOOL manual_click = argc == 4 && !strcmp(argv[1], "--click-field");
    POINT clicked = {0, 0};
    if (manual_click) {
        HWND root = GetAncestor(g.hwndFocus, GA_ROOT);
        char root_cls[128] = {0}; GetClassNameA(root, root_cls, sizeof(root_cls));
        RECT bounds; GetClientRect(root, &bounds);
        clicked.x = atoi(argv[2]); clicked.y = atoi(argv[3]);
        /* Only the account/password/verification input rows. Never click the
         * submit/consent controls behind Steam's keyboard. */
        if (strcmp(root_cls, "MPAY_LOGIN") || !IsWindowEnabled(root) ||
            clicked.x < bounds.right * .08 || clicked.x > bounds.right * .9 ||
            clicked.y < bounds.bottom * .32 || clicked.y > bounds.bottom * .56) {
            puts("null"); return 0;
        }
        HWND edit = restore_edit(root, GetWindowThreadProcessId(root, NULL), clicked.x, clicked.y);
        if (!edit) { puts("null"); return 0; }
        g.hwndFocus = edit;
        ClientToScreen(root, &clicked);
    }
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
    POINT mouse; if (manual_click) mouse = clicked; else GetCursorPos(&mouse);
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
