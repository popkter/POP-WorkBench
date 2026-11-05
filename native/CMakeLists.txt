cmake_minimum_required(VERSION 3.21)

project(poptools_terminal LANGUAGES C CXX)

# Generate the single QObject meta-object source as a normal build rule. CMake's
# AutoMoc helper uses libuv to spawn moc; that helper can be blocked by hardened
# Windows build hosts even though MSBuild is allowed to run moc directly.
set(CMAKE_AUTOMOC OFF)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick)
qt6_wrap_cpp(POPTOOLS_TERMINAL_MOC_SOURCES terminalitem.h)

set(LIBVTERM_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/libvterm")
set(LIBVTERM_SOURCES
    "${LIBVTERM_DIR}/src/encoding.c"
    "${LIBVTERM_DIR}/src/keyboard.c"
    "${LIBVTERM_DIR}/src/mouse.c"
    "${LIBVTERM_DIR}/src/parser.c"
    "${LIBVTERM_DIR}/src/pen.c"
    "${LIBVTERM_DIR}/src/screen.c"
    "${LIBVTERM_DIR}/src/state.c"
    "${LIBVTERM_DIR}/src/unicode.c"
    "${LIBVTERM_DIR}/src/vterm.c"
)

add_library(poptools_libvterm STATIC ${LIBVTERM_SOURCES})
target_include_directories(poptools_libvterm PUBLIC
    "${LIBVTERM_DIR}/include"
    PRIVATE
    "${LIBVTERM_DIR}/src"
)
target_compile_definitions(poptools_libvterm PRIVATE _CRT_SECURE_NO_WARNINGS)

add_library(poptools_terminal SHARED
    terminalitem.cpp
    terminalitem.h
    ${POPTOOLS_TERMINAL_MOC_SOURCES}
)

target_include_directories(poptools_terminal PRIVATE "${LIBVTERM_DIR}/include")
target_compile_definitions(poptools_terminal PRIVATE
    POPTOOLS_TERMINAL_LIBRARY
    _CRT_SECURE_NO_WARNINGS
)
target_link_libraries(poptools_terminal PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
    poptools_libvterm
)

set_target_properties(poptools_terminal PROPERTIES
    OUTPUT_NAME "poptools_terminal"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)

install(TARGETS poptools_terminal
    RUNTIME DESTINATION .
    LIBRARY DESTINATION .
)

include(CTest)
if(BUILD_TESTING)
    add_executable(poptools_libvterm_test terminal_core_test.c)
    target_link_libraries(poptools_libvterm_test PRIVATE poptools_libvterm)
    add_test(NAME poptools_libvterm_test COMMAND poptools_libvterm_test)
    add_executable(poptools_terminal_resize_test
        terminal_resize_test.cpp
        terminalitem.h
        ${POPTOOLS_TERMINAL_MOC_SOURCES}
    )
    # This test includes the implementation to exercise terminal internals.
    set_source_files_properties(terminal_resize_test.cpp PROPERTIES
        OBJECT_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/terminalitem.cpp")
    target_compile_definitions(poptools_terminal_resize_test PRIVATE POPTOOLS_TERMINAL_LIBRARY)
    target_link_libraries(poptools_terminal_resize_test PRIVATE
        Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick poptools_libvterm)
    add_test(NAME poptools_terminal_resize_test COMMAND poptools_terminal_resize_test)
    set_tests_properties(poptools_terminal_resize_test PROPERTIES
        TIMEOUT 20 ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
    if(WIN32)
        set_property(TEST poptools_terminal_resize_test APPEND PROPERTY
            ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:$<TARGET_FILE_DIR:Qt6::Core>")
    endif()
endif()
