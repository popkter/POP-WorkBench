#pragma once

#include <QColor>
#include <QFont>
#include <QHash>
#include <QInputMethodEvent>
#include <QPoint>
#include <QQuickPaintedItem>
#include <QTimer>

#include <array>

struct TerminalSession;

#if defined(_WIN32)
#  if defined(POPTOOLS_TERMINAL_LIBRARY)
#    define POPTOOLS_TERMINAL_EXPORT __declspec(dllexport)
#  else
#    define POPTOOLS_TERMINAL_EXPORT __declspec(dllimport)
#  endif
#else
#  define POPTOOLS_TERMINAL_EXPORT __attribute__((visibility("default")))
#endif

class TerminalItem : public QQuickPaintedItem
{
    Q_OBJECT
    Q_PROPERTY(QString sessionId READ sessionId WRITE setSessionId NOTIFY sessionIdChanged)
    Q_PROPERTY(qreal fontSize READ fontSize WRITE setFontSize NOTIFY fontSizeChanged)
    Q_PROPERTY(int columns READ columns NOTIFY terminalGeometryChanged)
    Q_PROPERTY(int rows READ rows NOTIFY terminalGeometryChanged)
    Q_PROPERTY(bool hasSelection READ hasSelection NOTIFY selectionChanged)
    Q_PROPERTY(int scrollbackLineCount READ scrollbackLineCount NOTIFY scrollbackChanged)
    Q_PROPERTY(int scrollOffset READ scrollOffset WRITE setScrollOffset NOTIFY scrollbackChanged)
    Q_PROPERTY(QColor foregroundColor READ foregroundColor WRITE setForegroundColor NOTIFY foregroundColorChanged)
    Q_PROPERTY(QColor selectionColor READ selectionColor WRITE setSelectionColor NOTIFY selectionColorChanged)
    Q_PROPERTY(QColor historySelectionColor READ historySelectionColor WRITE setHistorySelectionColor NOTIFY historySelectionColorChanged)

public:
    explicit TerminalItem(QQuickItem *parent = nullptr);
    ~TerminalItem() override;

    QString sessionId() const;
    void setSessionId(const QString &sessionId);
    qreal fontSize() const;
    void setFontSize(qreal size);
    int columns() const;
    int rows() const;
    bool hasSelection() const;
    int scrollbackLineCount() const;
    int scrollOffset() const;
    void setScrollOffset(int offset);
    QColor foregroundColor() const;
    void setForegroundColor(const QColor &color);
    QColor selectionColor() const;
    void setSelectionColor(const QColor &color);
    QColor historySelectionColor() const;
    void setHistorySelectionColor(const QColor &color);

    void paint(QPainter *painter) override;

    Q_INVOKABLE void feed(const QString &sessionId, const QString &text);
    Q_INVOKABLE void resetSession(const QString &sessionId);
    Q_INVOKABLE void removeSession(const QString &sessionId);
    Q_INVOKABLE void clearSelection();
    Q_INVOKABLE void copySelection();
    Q_INVOKABLE QString selectionText() const;
    Q_INVOKABLE void pasteClipboard();
    Q_INVOKABLE void pasteText(const QString &text);
    Q_INVOKABLE void selectAll();
    Q_INVOKABLE void scrollToBottom();

signals:
    void inputGenerated(const QString &sessionId, const QString &text);
    void terminalGeometryChanged();
    void terminalSizeChanged(int columns, int rows);
    void sessionIdChanged();
    void fontSizeChanged();
    void selectionChanged();
    void scrollbackChanged();
    void foregroundColorChanged();
    void selectionColorChanged();
    void historySelectionColorChanged();
    void terminalTitleChanged(const QString &sessionId, const QString &title);
    void bell(const QString &sessionId);
    void contextMenuRequested(qreal x, qreal y);

protected:
    void geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry) override;
    void keyPressEvent(QKeyEvent *event) override;
    void inputMethodEvent(QInputMethodEvent *event) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;
    void focusInEvent(QFocusEvent *event) override;
    void focusOutEvent(QFocusEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;

private:
    friend struct TerminalSession;

    TerminalSession *ensureSession(const QString &sessionId);
    TerminalSession *activeSession() const;
    void updateTextureSize();
    void updateMetrics();
    void updateTerminalSize();
    void restartCursorBlink();
    void sendText(const QString &text);
    void sendKey(int key, Qt::KeyboardModifiers modifiers);
    void emitSessionOutput(TerminalSession *session, const char *bytes, size_t length);
    void markSessionChanged(TerminalSession *session);
    QPoint cellAt(const QPointF &position) const;
    int viewportFirstLine(const TerminalSession *session) const;
    QString selectedText(const TerminalSession *session) const;
    bool cellSelected(const TerminalSession *session, int line, int column) const;
    void setSelectionEnd(TerminalSession *session, const QPoint &cell);
    void sendMouse(TerminalSession *session, const QPoint &cell, int button, bool pressed,
                   Qt::KeyboardModifiers modifiers);
    static int vtermModifiers(Qt::KeyboardModifiers modifiers);

    QHash<QString, TerminalSession *> m_sessions;
    QString m_sessionId;
    QFont m_font;
    QColor m_foregroundColor = QColor(0xe5, 0xe7, 0xeb);
    QColor m_selectionColor = QColor(0x66, 0x60, 0xc8, 0x80);
    QColor m_historySelectionColor = QColor(48, 68, 94);
    std::array<QFont, 16> m_cellFonts;
    qreal m_fontSize = 14.0;
    qreal m_cellWidth = 8.0;
    qreal m_cellHeight = 17.0;
    qreal m_baseline = 13.0;
    int m_columns = 120;
    int m_rows = 30;
    QString m_preedit;
    bool m_cursorBlinkOn = true;
    QTimer m_cursorTimer;
    QTimer m_geometryUpdateTimer;
};

extern "C" POPTOOLS_TERMINAL_EXPORT void poptools_register_terminal_type();
