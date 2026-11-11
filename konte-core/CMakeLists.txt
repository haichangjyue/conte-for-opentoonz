# konte-core: export kernel & format library (BSD-3-Clause)
# 纯逻辑内核可独立构建；接 OpenToonz 时用 -DKONTE_WITH_OPENTOONZ=ON 并传入 OT 头/库。
add_library(konte-core STATIC
  src/scene_plan.cpp
  src/export_kernel.cpp
  src/ot_scene_writer.cpp
)
target_include_directories(konte-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(konte-core PUBLIC cxx_std_17)
if(MSVC)
  target_compile_options(konte-core PRIVATE /utf-8)
endif()

option(KONTE_WITH_OPENTOONZ "Compile the OpenToonz scene writer (requires OT source + Qt/OpenCV deps)" OFF)
if(KONTE_WITH_OPENTOONZ)
  target_compile_definitions(konte-core PRIVATE KONTE_WITH_OPENTOONZ)
  # 由构建脚本 / 顶层传入（见仓库 scripts/build_kernel.ps1 与 KERNEL_CONTRACT.md）
  if(KONTE_OT_INCLUDE_DIRS)
    target_include_directories(konte-core PRIVATE ${KONTE_OT_INCLUDE_DIRS})
  endif()
  if(KONTE_OT_LIBS)
    target_link_libraries(konte-core PUBLIC ${KONTE_OT_LIBS})
  endif()

  # 当以 add_subdirectory 方式并入 OpenToonz 构建树时：直接复用 OT 的 include 与目标
  if(TARGET toonzlib)
    target_include_directories(konte-core PRIVATE
      ${CMAKE_SOURCE_DIR}/include
      ${CMAKE_SOURCE_DIR}
      ${QT_LIB_PATH}/include
      ${QT_LIB_PATH}/include/QtCore
      ${QT_LIB_PATH}/include/QtGui
      ${QT_LIB_PATH}/include/QtWidgets
      ${QT_LIB_PATH}/include/QtScript
      ${QT_LIB_PATH}/include/QtXml
      ${SDKROOT}/libjpeg-turbo/include
      ${SDKROOT}/zlib-1.2.8
      ${SDKROOT}/glut/3.7.6/include
      ${SDKROOT}/libmypaint/dist/64/include/libmypaint
    )
    target_link_libraries(konte-core PUBLIC
      toonzlib tnzcore tnzbase tnzext image
      Qt5::Core Qt5::Gui Qt5::Widgets Qt5::Script Qt5::Xml
    )
  endif()
endif()

add_executable(konte-export src/main.cpp)
target_link_libraries(konte-export PRIVATE konte-core)
if(MSVC)
  target_compile_options(konte-export PRIVATE /utf-8)
endif()

enable_testing()
add_executable(konte_core_tests tests/test_sceneplan.cpp)
target_link_libraries(konte_core_tests PRIVATE konte-core)
add_test(NAME konte_core_tests COMMAND konte_core_tests)
