#include "terminalitem.h"

#include <QClipboard>
#include <QFontDatabase>
#include <QFontMetricsF>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QWheelEvent>
#include <QtQml/qqml.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

extern "C" {
#include <vterm.h>
}

namespace {

constexpr int kScrollbackLimit = 10'000;
// QQuickPaintedItem already accounts for the window DPR. A modest additional
// scale keeps small terminal glyphs crisp after the painted texture is sampled
// by the Qt Quick scene graph, without the 4x memory cost of 2x supersampling.
constexpr qreal kTextRenderScale = 1.25;
constexpr int kFontBold = 1 << 0;
constexpr int kFontItalic = 1 << 1;
constexpr int kFontStrike = 1 << 2;
constexpr int kFontUnderline = 1 << 3;
// Match the terminal surface defined by the latest UI specification.
const QColor kDefaultBackground(0x2b, 0x31, 0x3d);
const QColor kDefaultForeground(0xe5, 0xe7, 0xeb);
const QColor kCursorColor(0xe5, 0xe7, 0xeb);
const QColor kSelectionColor(0x66, 0x60, 0xc8, 0x80);

using CellLine = std::vector<VTermScreenCell>;

QString cellText(const VTermScreenCell &cell)
{
    if (cell.chars[0] == UINT32_MAX)
        return {};
    QString text;
    for (const uint32_t codepoint : cell.chars) {
        if (codepoint == 0)
            break;
        const char32_t character = static_cast<char32_t>(codepoint);
        text.append(QString::fromUcs4(&character, 1));
    }
    return text;
}

QPoint orderedStart(const QPoint &a, const QPoint &b)
{
    return (a.y() < b.y() || (a.y() == b.y() && a.x() <= b.x())) ? a : b;
}

QPoint orderedEnd(const QPoint &a, const QPoint &b)
{
    return orderedStart(a, b) == a ? b : a;
}

} // namespace

struct TerminalSession
{
    explicit TerminalSession(TerminalItem *terminal, QString identifier, int rows, int columns)
        : owner(terminal), id(std::move(identifier)), vt(vterm_new(rows, columns))
    {
        vterm_set_utf8(vt, 1);
        screen = vterm_obtain_screen(vt);
        state = vterm_obtain_state(vt);
        vterm_screen_enable_altscreen(screen, 1);
        vterm_screen_enable_reflow(screen, true);
        vterm_screen_set_damage_merge(screen, VTERM_DAMAGE_ROW);
        vterm_output_set_callback(vt, outputCallback, this);
        vterm_screen_set_callbacks(screen, &callbacks, this);
        VTermColor foreground;
        VTermColor background;
        vterm_color_rgb(&foreground, kDefaultForeground.red(), kDefaultForeground.green(),
                        kDefaultForeground.blue());
        const QColor backgroundColor = owner->fillColor();
        vterm_color_rgb(&background, backgroundColor.red(), backgroundColor.green(),
                        backgroundColor.blue());
        vterm_screen_set_default_colors(screen, &foreground, &background);
        vterm_screen_reset(screen, 1);
    }

    ~TerminalSession()
    {
        vterm_free(vt);
    }

    void feed(const QByteArray &bytes)
    {
        if (!bytes.isEmpty()) {
            vterm_input_write(vt, bytes.constData(), static_cast<size_t>(bytes.size()));
            vterm_screen_flush_damage(screen);
        }
    }

    void resize(int rows, int columns)
    {
        vterm_set_size(vt, rows, columns);
        vterm_screen_flush_damage(screen);
    }

    void reset()
    {
        scrollback.clear();
        scrollOffset = 0;
        selectionActive = false;
        vterm_screen_reset(screen, 1);
        if (this == owner->activeSession()) {
            emit owner->selectionChanged();
            emit owner->scrollbackChanged();
        }
        owner->markSessionChanged(this);
    }

    static void outputCallback(const char *bytes, size_t length, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        session->owner->emitSessionOutput(session, bytes, length);
    }

    static int damageCallback(VTermRect, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        session->owner->markSessionChanged(session);
        return 1;
    }

    static int moveRectCallback(VTermRect, VTermRect, void *user)
    {
        return damageCallback({}, user);
    }

    static int moveCursorCallback(VTermPos position, VTermPos, int visible, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        session->cursor = QPoint(position.col, position.row);
        session->cursorVisible = visible != 0;
        session->owner->markSessionChanged(session);
        return 1;
    }

    static int propertyCallback(VTermProp property, VTermValue *value, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        if (property == VTERM_PROP_CURSORVISIBLE)
            session->cursorVisible = value->boolean != 0;
        else if (property == VTERM_PROP_CURSORSHAPE)
            session->cursorShape = value->number;
        else if (property == VTERM_PROP_MOUSE)
            session->mouseMode = value->number;
        else if (property == VTERM_PROP_TITLE) {
            if (value->string.initial)
                session->pendingTitle.clear();
            session->pendingTitle.append(QString::fromUtf8(value->string.str,
                                                            static_cast<qsizetype>(value->string.len)));
            if (value->string.final)
                emit session->owner->terminalTitleChanged(session->id, session->pendingTitle);
        }
        session->owner->markSessionChanged(session);
        return 1;
    }

    static int bellCallback(void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        emit session->owner->bell(session->id);
        return 1;
    }

    static int resizeCallback(int, int, void *user)
    {
        return damageCallback({}, user);
    }

    static int pushLineCallback(int columns, const VTermScreenCell *cells, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        session->scrollback.emplace_back(cells, cells + columns);
        if (session->scrollback.size() > kScrollbackLimit)
            session->scrollback.erase(session->scrollback.begin());
        if (session->scrollOffset > 0)
            session->scrollOffset = std::min(session->scrollOffset + 1,
                                             static_cast<int>(session->scrollback.size()));
        if (session == session->owner->activeSession())
            emit session->owner->scrollbackChanged();
        return 1;
    }

    static int popLineCallback(int columns, VTermScreenCell *cells, void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        if (session->scrollback.empty())
            return 0;
        const CellLine line = std::move(session->scrollback.back());
        session->scrollback.pop_back();
        // libvterm reuses this buffer and advances through it by cell.width.
        // Historical rows can be narrower than the current screen: initialize
        // the whole requested row so its tail cannot contain zero-width cells
        // (an infinite backfill loop) or stale text from another history line.
        VTermScreenCell blank{};
        blank.width = 1;
        vterm_state_get_default_colors(session->state, &blank.fg, &blank.bg);
        std::fill_n(cells, columns, blank);
        const int count = std::min(columns, static_cast<int>(line.size()));
        std::copy_n(line.begin(), count, cells);
        return 1;
    }

    static int clearScrollbackCallback(void *user)
    {
        auto *session = static_cast<TerminalSession *>(user);
        session->scrollback.clear();
        session->scrollOffset = 0;
        if (session == session->owner->activeSession())
            emit session->owner->scrollbackChanged();
        return 1;
    }

    inline static const VTermScreenCallbacks callbacks = {
        damageCallback,
        moveRectCallback,
        moveCursorCallback,
        propertyCallback,
        bellCallback,
        resizeCallback,
        pushLineCallback,
        popLineCallback,
        clearScrollbackCallback,
    };

    TerminalItem *owner;
    QString id;
    VTerm *vt = nullptr;
    VTermScreen *screen = nullptr;
    VTermState *state = nullptr;
    std::vector<CellLine> scrollback;
    QPoint cursor;
    bool cursorVisible = true;
    int cursorShape = VTERM_PROP_CURSORSHAPE_BAR_LEFT;
    int mouseMode = VTERM_PROP_MOUSE_NONE;
    int scrollOffset = 0;
    bool selectionActive = false;
    bool selecting = false;
    QPoint selectionAnchor;
    QPoint selectionExtent;
    QString pendingTitle;
};

TerminalItem::TerminalItem(QQuickItem *parent)
    : QQuickPaintedItem(parent)
{
    setFlag(ItemHasContents, true);
    setFlag(ItemAcceptsInputMethod, true);
    setAcceptedMouseButtons(Qt::AllButtons);
    setAcceptHoverEvents(true);
    setFocus(true);
    setAntialiasing(false);
    setSmooth(true);
    setOpaquePainting(true);
    setFillColor(kDefaultBackground);
    connect(this, &QQuickPaintedItem::fillColorChanged, this, [this] {
        const QColor backgroundColor = fillColor();
        for (auto *session : m_sessions) {
            VTermColor foreground;
            VTermColor background;
            vterm_state_get_default_colors(session->state, &foreground, &background);
            vterm_color_rgb(&background, backgroundColor.red(), backgroundColor.green(),
                            backgroundColor.blue());
            vterm_screen_set_default_colors(session->screen, &foreground, &background);
        }
        update();
    });
    m_cursorTimer.setInterval(530);
    connect(&m_cursorTimer, &QTimer::timeout, this, [this] {
        m_cursorBlinkOn = !m_cursorBlinkOn;
        update();
    });
    // Window maximize/restore can deliver a burst of geometry changes. Resizing
    // every libvterm session for each intermediate size repeats screen reflow
    // and scrollback transfers unnecessarily.
    m_geometryUpdateTimer.setSingleShot(true);
    m_geometryUpdateTimer.setInterval(40);
    connect(&m_geometryUpdateTimer, &QTimer::timeout, this, [this] {
        updateTextureSize();
        updateTerminalSize();
    });
    updateMetrics();
}

TerminalItem::~TerminalItem()
{
    qDeleteAll(m_sessions);
}

QString TerminalItem::sessionId() const { return m_sessionId; }

void TerminalItem::setSessionId(const QString &sessionId)
{
    if (m_sessionId == sessionId)
        return;
    m_sessionId = sessionId;
    ensureSession(sessionId);
    emit sessionIdChanged();
    emit selectionChanged();
    emit scrollbackChanged();
    update();
}

qreal TerminalItem::fontSize() const { return m_fontSize; }

void TerminalItem::setFontSize(qreal size)
{
    size = std::clamp(size, 8.0, 36.0);
    if (qFuzzyCompare(m_fontSize, size))
        return;
    m_fontSize = size;
    updateMetrics();
    emit fontSizeChanged();
}

int TerminalItem::columns() const { return m_columns; }
int TerminalItem::rows() const { return m_rows; }

bool TerminalItem::hasSelection() const
{
    const auto *session = activeSession();
    return session && session->selectionActive;
}

int TerminalItem::scrollbackLineCount() const
{
    const auto *session = activeSession();
    return session ? static_cast<int>(session->scrollback.size()) : 0;
}

int TerminalItem::scrollOffset() const
{
    const auto *session = activeSession();
    return session ? session->scrollOffset : 0;
}

void TerminalItem::setScrollOffset(int offset)
{
    auto *session = activeSession();
    if (!session)
        return;
    offset = std::clamp(offset, 0, static_cast<int>(session->scrollback.size()));
    if (session->scrollOffset == offset)
        return;
    session->scrollOffset = offset;
    emit scrollbackChanged();
    update();
}

TerminalSession *TerminalItem::ensureSession(const QString &sessionId)
{
    if (sessionId.isEmpty())
        return nullptr;
    const auto existing = m_sessions.find(sessionId);
    if (existing != m_sessions.end())
        return existing.value();
    auto *session = new TerminalSession(this, sessionId, m_rows, m_columns);
    m_sessions.insert(sessionId, session);
    return session;
}

TerminalSession *TerminalItem::activeSession() const
{
    const auto iterator = m_sessions.constFind(m_sessionId);
    return iterator == m_sessions.constEnd() ? nullptr : iterator.value();
}

void TerminalItem::feed(const QString &sessionId, const QString &text)
{
    auto *session = ensureSession(sessionId);
    if (session)
        session->feed(text.toUtf8());
}

void TerminalItem::resetSession(const QString &sessionId)
{
    if (auto *session = ensureSession(sessionId))
        session->reset();
}

void TerminalItem::removeSession(const QString &sessionId)
{
    const bool active = sessionId == m_sessionId;
    delete m_sessions.take(sessionId);
    if (active) {
        emit selectionChanged();
        emit scrollbackChanged();
    }
    update();
}

void TerminalItem::clearSelection()
{
    if (auto *session = activeSession()) {
        if (!session->selectionActive)
            return;
        session->selectionActive = false;
        emit selectionChanged();
        update();
    }
}

QString TerminalItem::selectionText() const
{
    const auto *session = activeSession();
    return session ? selectedText(session) : QString();
}

void TerminalItem::copySelection()
{
    if (const auto *session = activeSession()) {
        const QString text = selectedText(session);
        if (!text.isEmpty())
            QGuiApplication::clipboard()->setText(text);
    }
}

void TerminalItem::pasteClipboard()
{
    pasteText(QGuiApplication::clipboard()->text());
}

void TerminalItem::pasteText(const QString &value)
{
    auto *session = activeSession();
    if (!session)
        return;
    QString text = value;
    if (text.isEmpty())
        return;
    text.replace(QStringLiteral("\r\n"), QStringLiteral("\r"));
    text.replace(QLatin1Char('\n'), QLatin1Char('\r'));
    vterm_keyboard_start_paste(session->vt);
    emit inputGenerated(session->id, text);
    vterm_keyboard_end_paste(session->vt);
}

void TerminalItem::selectAll()
{
    auto *session = activeSession();
    if (!session)
        return;
    session->selectionAnchor = QPoint(0, 0);
    session->selectionExtent = QPoint(m_columns - 1,
                                      static_cast<int>(session->scrollback.size()) + m_rows - 1);
    session->selectionActive = true;
    emit selectionChanged();
    update();
}

void TerminalItem::scrollToBottom()
{
    if (auto *session = activeSession()) {
        if (session->scrollOffset == 0)
            return;
        session->scrollOffset = 0;
        emit scrollbackChanged();
        update();
    }
}

void TerminalItem::updateMetrics()
{
    QString family = QStringLiteral("Cascadia Mono");
    const QStringList families = QFontDatabase::families();
    if (!families.contains(family))
        family = families.contains(QStringLiteral("Consolas"))
            ? QStringLiteral("Consolas")
            : QFontDatabase::systemFont(QFontDatabase::FixedFont).family();
    m_font = QFont(family);
    m_font.setStyleHint(QFont::Monospace);
    m_font.setStyleStrategy(static_cast<QFont::StyleStrategy>(QFont::PreferAntialias
                                                              | QFont::PreferQuality));
    m_font.setHintingPreference(QFont::PreferFullHinting);
    m_font.setFixedPitch(true);
    m_font.setPixelSize(qRound(m_fontSize));
    for (int style = 0; style < static_cast<int>(m_cellFonts.size()); ++style) {
        QFont font = m_font;
        font.setBold(style & kFontBold);
        font.setItalic(style & kFontItalic);
        font.setStrikeOut(style & kFontStrike);
        font.setUnderline(style & kFontUnderline);
        m_cellFonts[static_cast<size_t>(style)] = std::move(font);
    }
    const QFontMetricsF metrics(m_font);
    m_cellWidth = std::max<qreal>(1.0, std::ceil(metrics.horizontalAdvance(QStringLiteral("M"))));
    m_cellHeight = std::max<qreal>(1.0, std::ceil(metrics.height() * 1.18));
    m_baseline = std::ceil((m_cellHeight - metrics.height()) / 2.0 + metrics.ascent());
    updateTerminalSize();
    update();
}

void TerminalItem::updateTextureSize()
{
    const QSize size(qMax(1, qCeil(width() * kTextRenderScale)),
                     qMax(1, qCeil(height() * kTextRenderScale)));
    if (textureSize() != size)
        setTextureSize(size);
}

void TerminalItem::updateTerminalSize()
{
    const int columns = std::max(2, static_cast<int>(std::floor(width() / m_cellWidth)));
    const int rows = std::max(1, static_cast<int>(std::floor(height() / m_cellHeight)));
    if (columns == m_columns && rows == m_rows)
        return;
    m_columns = columns;
    m_rows = rows;
    for (auto *session : m_sessions)
        session->resize(m_rows, m_columns);
    emit terminalGeometryChanged();
    emit terminalSizeChanged(m_columns, m_rows);
    update();
}

void TerminalItem::geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry)
{
    QQuickPaintedItem::geometryChange(newGeometry, oldGeometry);
    m_geometryUpdateTimer.start();
}

QColor terminalColor(VTermScreen *screen, VTermColor color, const QColor &fallback)
{
    if (color.type & VTERM_COLOR_DEFAULT_MASK)
        return fallback;
    vterm_screen_convert_color_to_rgb(screen, &color);
    return QColor(color.rgb.red, color.rgb.green, color.rgb.blue);
}

int TerminalItem::viewportFirstLine(const TerminalSession *session) const
{
    const int total = static_cast<int>(session->scrollback.size()) + m_rows;
    return std::max(0, total - m_rows - session->scrollOffset);
}

void TerminalItem::paint(QPainter *painter)
{
    const QColor backgroundColor = fillColor();
    painter->fillRect(boundingRect(), backgroundColor);
    painter->setFont(m_font);
    painter->setPen(kDefaultForeground);
    painter->setRenderHint(QPainter::Antialiasing, false);
    painter->setRenderHint(QPainter::TextAntialiasing, true);
    const auto *session = activeSession();
    if (!session)
        return;

    const int scrollbackRows = static_cast<int>(session->scrollback.size());
    const int firstLine = viewportFirstLine(session);
    int activeFontStyle = 0;
    QColor activeForeground = kDefaultForeground;
    for (int displayRow = 0; displayRow < m_rows; ++displayRow) {
        const int line = firstLine + displayRow;
        for (int column = 0; column < m_columns; ++column) {
            VTermScreenCell cell{};
            bool valid = false;
            if (line < scrollbackRows) {
                const CellLine &historyLine = session->scrollback[static_cast<size_t>(line)];
                if (column < static_cast<int>(historyLine.size())) {
                    cell = historyLine[static_cast<size_t>(column)];
                    valid = true;
                }
            } else {
                const int screenRow = line - scrollbackRows;
                if (screenRow >= 0 && screenRow < m_rows) {
                    valid = vterm_screen_get_cell(session->screen, {screenRow, column}, &cell) != 0;
                }
            }
            // libvterm marks the continuation half of a wide glyph with
            // UINT32_MAX. Its background was already painted by the leading
            // cell; repainting it here would erase the right half of CJK text.
            if (valid && cell.chars[0] == UINT32_MAX)
                continue;
            const QRectF cellRect(column * m_cellWidth, displayRow * m_cellHeight,
                                  m_cellWidth * std::max(1, valid ? static_cast<int>(cell.width) : 1),
                                  m_cellHeight);
            QColor background = backgroundColor;
            if (valid) {
                if (cell.attrs.reverse)
                    background = terminalColor(session->screen, cell.fg, kDefaultForeground);
                else if (!(cell.bg.type & VTERM_COLOR_DEFAULT_MASK))
                    background = terminalColor(session->screen, cell.bg, backgroundColor);
            }
            if (background != backgroundColor)
                painter->fillRect(cellRect, background);
            if (cellSelected(session, line, column))
                painter->fillRect(cellRect, kSelectionColor);
            if (!valid)
                continue;
            const QString text = cellText(cell);
            if (text.isEmpty() || cell.attrs.conceal)
                continue;

            QColor foreground = kDefaultForeground;
            if (cell.attrs.reverse)
                foreground = terminalColor(session->screen, cell.bg, backgroundColor);
            else if (!(cell.fg.type & VTERM_COLOR_DEFAULT_MASK))
                foreground = terminalColor(session->screen, cell.fg, kDefaultForeground);
            if (cell.attrs.faint)
                foreground.setAlphaF(foreground.alphaF() * 0.55);

            const int fontStyle = (cell.attrs.bold ? kFontBold : 0)
                | (cell.attrs.italic ? kFontItalic : 0)
                | (cell.attrs.strike ? kFontStrike : 0)
                | (cell.attrs.underline != VTERM_UNDERLINE_OFF ? kFontUnderline : 0);
            if (fontStyle != activeFontStyle) {
                painter->setFont(m_cellFonts[static_cast<size_t>(fontStyle)]);
                activeFontStyle = fontStyle;
            }
            if (foreground != activeForeground) {
                painter->setPen(foreground);
                activeForeground = foreground;
            }
            painter->drawText(QPointF(cellRect.left(), cellRect.top() + m_baseline), text);
        }
    }

    if (session->scrollOffset == 0 && session->cursorVisible && m_cursorBlinkOn && hasActiveFocus()) {
        const QRectF cursorRect(session->cursor.x() * m_cellWidth,
                                session->cursor.y() * m_cellHeight,
                                m_cellWidth, m_cellHeight);
        if (session->cursorShape == VTERM_PROP_CURSORSHAPE_UNDERLINE) {
            painter->fillRect(QRectF(cursorRect.left(), cursorRect.bottom() - 2,
                                     cursorRect.width(), 2), kCursorColor);
        } else if (session->cursorShape == VTERM_PROP_CURSORSHAPE_BAR_LEFT) {
            painter->fillRect(QRectF(cursorRect.left(), cursorRect.top(), 2,
                                     cursorRect.height()), kCursorColor);
        } else {
            painter->fillRect(cursorRect, kCursorColor);
            VTermScreenCell cursorCell{};
            if (vterm_screen_get_cell(session->screen,
                                      {session->cursor.y(), session->cursor.x()},
                                      &cursorCell)
                && cursorCell.width > 0) {
                painter->setFont(m_font);
                painter->setPen(backgroundColor);
                painter->drawText(QPointF(cursorRect.left(), cursorRect.top() + m_baseline),
                                  cellText(cursorCell));
            }
        }
    }

    if (!m_preedit.isEmpty()) {
        painter->setFont(m_font);
        painter->setPen(kDefaultForeground);
        const qreal x = session->cursor.x() * m_cellWidth;
        const qreal y = session->cursor.y() * m_cellHeight;
        const QRectF preeditRect(x, y, std::max(m_cellWidth, m_preedit.size() * m_cellWidth),
                                 m_cellHeight);
        painter->fillRect(preeditRect, backgroundColor);
        painter->drawText(QPointF(x, y + m_baseline), m_preedit);
        painter->drawLine(QPointF(x, y + m_cellHeight - 1),
                          QPointF(preeditRect.right(), y + m_cellHeight - 1));
    }
}

int TerminalItem::vtermModifiers(Qt::KeyboardModifiers modifiers)
{
    int result = VTERM_MOD_NONE;
    if (modifiers.testFlag(Qt::ShiftModifier)) result |= VTERM_MOD_SHIFT;
    if (modifiers.testFlag(Qt::AltModifier)) result |= VTERM_MOD_ALT;
    if (modifiers.testFlag(Qt::ControlModifier)) result |= VTERM_MOD_CTRL;
    return result;
}

void TerminalItem::sendKey(int key, Qt::KeyboardModifiers modifiers)
{
    if (auto *session = activeSession())
        vterm_keyboard_key(session->vt, static_cast<VTermKey>(key),
                           static_cast<VTermModifier>(vtermModifiers(modifiers)));
}

void TerminalItem::sendText(const QString &text)
{
    auto *session = activeSession();
    if (!session)
        return;
    const auto codepoints = text.toUcs4();
    for (const uint codepoint : codepoints)
        vterm_keyboard_unichar(session->vt, codepoint, VTERM_MOD_NONE);
}

void TerminalItem::keyPressEvent(QKeyEvent *event)
{
    restartCursorBlink();
    const auto modifiers = event->modifiers();
    if (modifiers.testFlag(Qt::ControlModifier) && modifiers.testFlag(Qt::ShiftModifier)) {
        if (event->key() == Qt::Key_C) { copySelection(); event->accept(); return; }
        if (event->key() == Qt::Key_V) { pasteClipboard(); event->accept(); return; }
    }
    if (event->key() == Qt::Key_Insert && modifiers.testFlag(Qt::ShiftModifier)) {
        pasteClipboard(); event->accept(); return;
    }
    if (event->key() == Qt::Key_Insert && modifiers.testFlag(Qt::ControlModifier)) {
        copySelection(); event->accept(); return;
    }

    int terminalKey = VTERM_KEY_NONE;
    switch (event->key()) {
    case Qt::Key_Return: case Qt::Key_Enter: terminalKey = VTERM_KEY_ENTER; break;
    case Qt::Key_Tab: case Qt::Key_Backtab: terminalKey = VTERM_KEY_TAB; break;
    case Qt::Key_Backspace: terminalKey = VTERM_KEY_BACKSPACE; break;
    case Qt::Key_Escape: terminalKey = VTERM_KEY_ESCAPE; break;
    case Qt::Key_Up: terminalKey = VTERM_KEY_UP; break;
    case Qt::Key_Down: terminalKey = VTERM_KEY_DOWN; break;
    case Qt::Key_Left: terminalKey = VTERM_KEY_LEFT; break;
    case Qt::Key_Right: terminalKey = VTERM_KEY_RIGHT; break;
    case Qt::Key_Insert: terminalKey = VTERM_KEY_INS; break;
    case Qt::Key_Delete: terminalKey = VTERM_KEY_DEL; break;
    case Qt::Key_Home: terminalKey = VTERM_KEY_HOME; break;
    case Qt::Key_End: terminalKey = VTERM_KEY_END; break;
    case Qt::Key_PageUp: terminalKey = VTERM_KEY_PAGEUP; break;
    case Qt::Key_PageDown: terminalKey = VTERM_KEY_PAGEDOWN; break;
    default:
        if (event->key() >= Qt::Key_F1 && event->key() <= Qt::Key_F35)
            terminalKey = VTERM_KEY_FUNCTION(event->key() - Qt::Key_F1 + 1);
        break;
    }
    if (terminalKey != VTERM_KEY_NONE) {
        sendKey(terminalKey, modifiers);
        event->accept();
        return;
    }
    auto *session = activeSession();
    if (session && !event->text().isEmpty()) {
        const auto codepoints = event->text().toUcs4();
        for (const uint codepoint : codepoints)
            vterm_keyboard_unichar(session->vt, codepoint,
                                   static_cast<VTermModifier>(vtermModifiers(modifiers)));
        event->accept();
        return;
    }
    QQuickPaintedItem::keyPressEvent(event);
}

void TerminalItem::inputMethodEvent(QInputMethodEvent *event)
{
    restartCursorBlink();
    if (!event->commitString().isEmpty())
        sendText(event->commitString());
    m_preedit = event->preeditString();
    update();
    event->accept();
}

QVariant TerminalItem::inputMethodQuery(Qt::InputMethodQuery query) const
{
    const auto *session = activeSession();
    if (query == Qt::ImEnabled)
        return true;
    if (query == Qt::ImCursorRectangle && session) {
        return QRectF(session->cursor.x() * m_cellWidth, session->cursor.y() * m_cellHeight,
                      m_cellWidth, m_cellHeight);
    }
    return QQuickPaintedItem::inputMethodQuery(query);
}

void TerminalItem::focusInEvent(QFocusEvent *event)
{
    if (auto *session = activeSession())
        vterm_state_focus_in(session->state);
    restartCursorBlink();
    update();
    QQuickPaintedItem::focusInEvent(event);
}

void TerminalItem::focusOutEvent(QFocusEvent *event)
{
    if (auto *session = activeSession())
        vterm_state_focus_out(session->state);
    m_cursorTimer.stop();
    update();
    QQuickPaintedItem::focusOutEvent(event);
}

void TerminalItem::restartCursorBlink()
{
    m_cursorBlinkOn = true;
    if (hasActiveFocus())
        m_cursorTimer.start();
}

QPoint TerminalItem::cellAt(const QPointF &position) const
{
    const auto *session = activeSession();
    const int firstLine = session ? viewportFirstLine(session) : 0;
    return QPoint(std::clamp(static_cast<int>(position.x() / m_cellWidth), 0, m_columns - 1),
                  firstLine + std::clamp(static_cast<int>(position.y() / m_cellHeight), 0, m_rows - 1));
}

void TerminalItem::setSelectionEnd(TerminalSession *session, const QPoint &cell)
{
    session->selectionExtent = cell;
    session->selectionActive = session->selectionAnchor != session->selectionExtent;
    emit selectionChanged();
    update();
}

void TerminalItem::sendMouse(TerminalSession *session, const QPoint &cell, int button, bool pressed,
                             Qt::KeyboardModifiers modifiers)
{
    const int screenRow = cell.y() - static_cast<int>(session->scrollback.size());
    if (screenRow < 0 || screenRow >= m_rows)
        return;
    vterm_mouse_move(session->vt, screenRow, cell.x(),
                     static_cast<VTermModifier>(vtermModifiers(modifiers)));
    vterm_mouse_button(session->vt, button, pressed,
                       static_cast<VTermModifier>(vtermModifiers(modifiers)));
}

void TerminalItem::mousePressEvent(QMouseEvent *event)
{
    forceActiveFocus();
    auto *session = activeSession();
    if (!session)
        return;
    const QPoint cell = cellAt(event->position());
    if (session->mouseMode != VTERM_PROP_MOUSE_NONE && !event->modifiers().testFlag(Qt::ShiftModifier)) {
        const int button = event->button() == Qt::LeftButton ? 1
            : event->button() == Qt::MiddleButton ? 2 : 3;
        sendMouse(session, cell, button, true, event->modifiers());
    } else if (event->button() == Qt::LeftButton) {
        session->selectionAnchor = cell;
        session->selectionExtent = cell;
        session->selectionActive = false;
        session->selecting = true;
        emit selectionChanged();
        update();
    } else if (event->button() == Qt::MiddleButton) {
        pasteClipboard();
    } else if (event->button() == Qt::RightButton) {
        emit contextMenuRequested(event->position().x(), event->position().y());
    }
    event->accept();
}

void TerminalItem::mouseDoubleClickEvent(QMouseEvent *event)
{
    auto *session = activeSession();
    if (!session || event->button() != Qt::LeftButton
        || (session->mouseMode != VTERM_PROP_MOUSE_NONE
            && !event->modifiers().testFlag(Qt::ShiftModifier))) {
        QQuickPaintedItem::mouseDoubleClickEvent(event);
        return;
    }

    const QPoint cell = cellAt(event->position());
    const int scrollbackRows = static_cast<int>(session->scrollback.size());
    const auto textAt = [this, session, scrollbackRows, row = cell.y()](int column) {
        VTermScreenCell terminalCell{};
        bool valid = false;
        if (row < scrollbackRows) {
            const CellLine &history = session->scrollback[static_cast<size_t>(row)];
            if (column < static_cast<int>(history.size())) {
                terminalCell = history[static_cast<size_t>(column)];
                valid = true;
            }
        } else {
            const int screenRow = row - scrollbackRows;
            valid = screenRow >= 0 && screenRow < m_rows
                && vterm_screen_get_cell(session->screen, {screenRow, column}, &terminalCell) != 0;
        }
        return valid && terminalCell.width > 0 ? cellText(terminalCell) : QStringLiteral(" ");
    };
    const auto isWordCell = [&textAt](int column) {
        const QString text = textAt(column);
        return !text.isEmpty() && !text.front().isSpace();
    };

    int first = cell.x();
    int last = cell.x();
    if (isWordCell(cell.x())) {
        while (first > 0 && isWordCell(first - 1))
            --first;
        while (last + 1 < m_columns && isWordCell(last + 1))
            ++last;
    }
    session->selectionAnchor = QPoint(first, cell.y());
    session->selectionExtent = QPoint(last, cell.y());
    session->selectionActive = true;
    session->selecting = false;
    emit selectionChanged();
    update();
    event->accept();
}

void TerminalItem::mouseMoveEvent(QMouseEvent *event)
{
    auto *session = activeSession();
    if (!session)
        return;
    const QPoint cell = cellAt(event->position());
    if (session->mouseMode != VTERM_PROP_MOUSE_NONE && !event->modifiers().testFlag(Qt::ShiftModifier)) {
        const bool pressed = event->buttons().testFlag(Qt::LeftButton);
        sendMouse(session, cell, 1, pressed, event->modifiers());
    } else if (session->selecting) {
        setSelectionEnd(session, cell);
    }
    event->accept();
}

void TerminalItem::mouseReleaseEvent(QMouseEvent *event)
{
    auto *session = activeSession();
    if (!session)
        return;
    const QPoint cell = cellAt(event->position());
    if (session->mouseMode != VTERM_PROP_MOUSE_NONE && !event->modifiers().testFlag(Qt::ShiftModifier)) {
        const int button = event->button() == Qt::LeftButton ? 1
            : event->button() == Qt::MiddleButton ? 2 : 3;
        sendMouse(session, cell, button, false, event->modifiers());
    }
    session->selecting = false;
    event->accept();
}

void TerminalItem::wheelEvent(QWheelEvent *event)
{
    auto *session = activeSession();
    if (!session)
        return;
    if (session->mouseMode != VTERM_PROP_MOUSE_NONE && !event->modifiers().testFlag(Qt::ShiftModifier)) {
        const QPoint cell = cellAt(event->position());
        const int button = event->angleDelta().y() > 0 ? 4 : 5;
        sendMouse(session, cell, button, true, event->modifiers());
        sendMouse(session, cell, button, false, event->modifiers());
    } else {
        const int lines = std::max(1, std::abs(event->angleDelta().y()) / 40);
        session->scrollOffset = std::clamp(
            session->scrollOffset + (event->angleDelta().y() > 0 ? lines : -lines),
            0, static_cast<int>(session->scrollback.size()));
        emit scrollbackChanged();
        update();
    }
    event->accept();
}

bool TerminalItem::cellSelected(const TerminalSession *session, int line, int column) const
{
    if (!session->selectionActive)
        return false;
    const QPoint start = orderedStart(session->selectionAnchor, session->selectionExtent);
    const QPoint end = orderedEnd(session->selectionAnchor, session->selectionExtent);
    if (line < start.y() || line > end.y())
        return false;
    if (start.y() == end.y())
        return line == start.y() && column >= start.x() && column <= end.x();
    if (line == start.y()) return column >= start.x();
    if (line == end.y()) return column <= end.x();
    return true;
}

QString TerminalItem::selectedText(const TerminalSession *session) const
{
    if (!session->selectionActive)
        return {};
    const QPoint start = orderedStart(session->selectionAnchor, session->selectionExtent);
    const QPoint end = orderedEnd(session->selectionAnchor, session->selectionExtent);
    QStringList lines;
    const int scrollbackRows = static_cast<int>(session->scrollback.size());
    for (int line = start.y(); line <= end.y(); ++line) {
        QString text;
        const int firstColumn = line == start.y() ? start.x() : 0;
        const int lastColumn = line == end.y() ? end.x() : m_columns - 1;
        for (int column = firstColumn; column <= lastColumn; ++column) {
            VTermScreenCell cell{};
            bool valid = false;
            if (line < scrollbackRows) {
                const CellLine &history = session->scrollback[static_cast<size_t>(line)];
                if (column < static_cast<int>(history.size())) {
                    cell = history[static_cast<size_t>(column)];
                    valid = true;
                }
            } else {
                const int row = line - scrollbackRows;
                valid = row >= 0 && row < m_rows
                    && vterm_screen_get_cell(session->screen, {row, column}, &cell) != 0;
            }
            if (valid && cell.width > 0)
                text.append(cellText(cell));
            else if (!valid || cell.width != 0)
                text.append(QLatin1Char(' '));
        }
        while (text.endsWith(QLatin1Char(' ')))
            text.chop(1);
        lines.append(text);
    }
    return lines.join(QLatin1Char('\n'));
}

void TerminalItem::emitSessionOutput(TerminalSession *session, const char *bytes, size_t length)
{
    emit inputGenerated(session->id,
                        QString::fromUtf8(bytes, static_cast<qsizetype>(length)));
}

void TerminalItem::markSessionChanged(TerminalSession *session)
{
    if (session == activeSession())
        update();
}

extern "C" POPTOOLS_TERMINAL_EXPORT void poptools_register_terminal_type()
{
    qmlRegisterType<TerminalItem>("PopTools.Terminal", 1, 0, "TerminalView");
}
