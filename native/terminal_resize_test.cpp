#include "terminalitem.cpp"

#include <QEventLoop>
#include <cstdio>

// Exercise the actual scrollback callbacks, including a buffer that was last
// used at a wider size. A zero-width padding cell makes libvterm's backfill
// loop stop advancing when the window grows vertically.
int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    for (const auto background : {QColor("#ffffff"), QColor("#171c24")}) {
        const QColor ink = readableForeground(QColor("#e5e7eb"), background);
        const qreal fg = luminance(ink), bg = luminance(background);
        if ((std::max(fg, bg) + 0.05) / (std::min(fg, bg) + 0.05) < 4.5)
            return 6;
    }
    TerminalItem input;
    input.setSize(QSizeF(800, 400));
    // Terminal sizing is debounced; let the real geometry timer apply it.
    QEventLoop layout;
    QTimer::singleShot(100, &layout, &QEventLoop::quit);
    layout.exec();
    input.setSessionId(QStringLiteral("input-test"));
    input.feed(input.sessionId(), QStringLiteral("history\r\n").repeated(100));
    input.setForegroundColor(QColor("#20252b"));
    input.setFillColor(QColor("#ffffff"));
    if (input.foregroundColor() != QColor("#20252b") || input.scrollbackLineCount() == 0)
        return 7;
    for (const auto key : {Qt::Key_Return, Qt::Key_Enter}) {
        input.setScrollOffset(10);
        if (input.scrollOffset() != 10)
            return 4;
        bool submittedAtBottom = false;
        const auto connection = QObject::connect(
            &input, &TerminalItem::inputGenerated,
            [&input, &submittedAtBottom](const QString &, const QString &text) {
                submittedAtBottom = text == QStringLiteral("\r") && input.scrollOffset() == 0;
            });
        QKeyEvent enter(QEvent::KeyPress, key, Qt::NoModifier);
        QCoreApplication::sendEvent(&input, &enter);
        QObject::disconnect(connection);
        if (!submittedAtBottom || input.scrollOffset() != 0)
            return 5;
    }
    TerminalItem owner;
    TerminalSession session(&owner, QStringLiteral("resize-test"), 24, 80);
    VTermScreenCell blank{};
    blank.width = 1;
    vterm_state_get_default_colors(session.state, &blank.fg, &blank.bg);
    CellLine narrow(80, blank);
    narrow[0].chars[0] = 'A';
    TerminalSession::pushLineCallback(80, narrow.data(), &session);
    CellLine restored(160);
    TerminalSession::popLineCallback(160, restored.data(), &session);
    for (int col = 80; col < 160; ++col) {
        if (restored[col].width != 1 || restored[col].chars[0] != 0) {
            std::fprintf(stderr, "Invalid padding at column %d: width=%d\n",
                         col, restored[col].width);
            return 1;
        }
    }
    // Previously used buffers must not leak stale text into the restored row.
    TerminalSession::pushLineCallback(80, narrow.data(), &session);
    for (auto &cell : restored) {
        cell = blank;
        cell.chars[0] = 'X';
    }
    TerminalSession::popLineCallback(160, restored.data(), &session);
    if (restored[0].chars[0] != 'A' || restored[159].chars[0] != 0)
        return 2;
    for (int cycle = 0; cycle < 100; ++cycle) {
        session.resize(24, 80);
        session.feed(QByteArray("A \xe7\x95\x8c prompt\r\n").repeated(100));
        session.resize(24, 160);
        session.resize(48, 160);
        session.resize(24, 80);
    }
    session.scrollback.clear();
    for (int row = 0; row < kScrollbackLimit + 500; ++row) {
        narrow[0].chars[0] = static_cast<uint32_t>(row + 1);
        TerminalSession::pushLineCallback(80, narrow.data(), &session);
    }
    if (session.scrollback.size() != kScrollbackLimit
        || session.scrollback.front()[0].chars[0] != 501
        || session.scrollback.back()[0].chars[0] != kScrollbackLimit + 500)
        return 3;
    return 0;
}
