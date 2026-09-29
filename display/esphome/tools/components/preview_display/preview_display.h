#pragma once

#include <string>
#include <vector>

#include "esphome/components/display/display.h"

namespace esphome::preview_display {

// Draws like epaper_spi (COLOR_ON is white, clear() fills white) into a 1-bit
// buffer, and render() writes the result to a binary PBM file.
class PreviewDisplay : public display::Display {
 public:
  PreviewDisplay(int width, int height) : width_(width), height_(height), pixels_(width * height, false) {}

  void update() override { this->do_update_(); }
  // Draw the current state and write it to `path`.
  void render(const std::string &path);

  void draw_pixel_at(int x, int y, Color color) override;
  void clear() override { this->fill(display::COLOR_ON); }
  void fill(Color color) override;
  display::DisplayType get_display_type() override { return display::DISPLAY_TYPE_BINARY; }

 protected:
  int get_width_internal() override { return this->width_; }
  int get_height_internal() override { return this->height_; }
  static bool is_black(Color c) { return c.r + c.g + c.b < 382; }  // as epaper_spi decides

  int width_;
  int height_;
  std::vector<bool> pixels_;  // true is black
};

}  // namespace esphome::preview_display
