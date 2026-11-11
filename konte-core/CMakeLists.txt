# konte-core: export kernel & format library (BSD-3-Clause)
add_library(konte-core STATIC
  src/placeholder.cpp
)
target_include_directories(konte-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
# TODO: 依据 PoC(P1/P4) 接入 OT 场景/渲染 API 与 PDF 叠图实现。
