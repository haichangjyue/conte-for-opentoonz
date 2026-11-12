# SPDX-License-Identifier: BSD-3-Clause
cmake_minimum_required(VERSION 3.16)
project(konte-bridge-qt LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 需要 Qt5 Core/Network（不需要 QtWebSockets：WS 为手写实现）
find_package(Qt5 COMPONENTS Core Network Gui REQUIRED)

add_executable(konte-bridge-qt src/main.cpp)
target_link_libraries(konte-bridge-qt PRIVATE Qt5::Core Qt5::Network Qt5::Gui)
if(WIN32)
  target_link_libraries(konte-bridge-qt PRIVATE ws2_32)
endif()
