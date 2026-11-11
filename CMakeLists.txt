cmake_minimum_required(VERSION 3.16)
project(konte-for-opentoonz LANGUAGES CXX)

# 说明：完整 OpenToonz 构建沿用上游 OT 的 CMake。
# 本文件是最小占位 / 组合构建入口。实际开发时把 OpenToonz 源码置于 toonz/（或 submodule），
# 并在其构建系统中 include 本模块。

option(KONTE_BUILD_CORE "Build konte-core" ON)
if(KONTE_BUILD_CORE)
  add_subdirectory(konte-core)
endif()

# 可选：若存在同级的私有仓库 konte-studio，则并入发行构建（不纳入公开仓）
if(EXISTS "${CMAKE_SOURCE_DIR}/../konte-studio/CMakeLists.txt")
  message(STATUS "Found private konte-studio — including into release build")
  add_subdirectory("${CMAKE_SOURCE_DIR}/../konte-studio" "${CMAKE_BINARY_DIR}/konte-studio")
endif()
