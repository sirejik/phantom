#include <iostream>

#include "phantom/maintenance.hpp"
int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "expected build id required\n";
    return 1;
  }
  try {
    return phantom::maintenance_integration(argv[1]);
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
