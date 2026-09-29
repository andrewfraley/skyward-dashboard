#include "preview_display.h"

#include <cstdio>

#include "esphome/core/log.h"

namespace esphome::preview_display {

static const char *const TAG = "preview_display";

void PreviewDisplay::draw_pixel_at(int x, int y, Color color) {
  if (x < 0 || y < 0 || x >= this->width_ || y >= this->height_)
    return;
  this->pixels_[y * this->width_ + x] = is_black(color);
}

void PreviewDisplay::fill(Color color) { std::fill(this->pixels_.begin(), this->pixels_.end(), is_black(color)); }

void PreviewDisplay::render(const std::string &path) {
  this->do_update_();
  FILE *f = fopen(path.c_str(), "wb");
  if (f == nullptr) {
    ESP_LOGE(TAG, "Can't write %s", path.c_str());
    return;
  }
  fprintf(f, "P4\n%d %d\n", this->width_, this->height_);
  const int row_bytes = (this->width_ + 7) / 8;
  std::vector<uint8_t> row(row_bytes);
  for (int y = 0; y < this->height_; y++) {
    std::fill(row.begin(), row.end(), 0);
    for (int x = 0; x < this->width_; x++) {
      if (this->pixels_[y * this->width_ + x])
        row[x / 8] |= 0x80 >> (x % 8);
    }
    fwrite(row.data(), 1, row_bytes, f);
  }
  fclose(f);
  ESP_LOGI(TAG, "Wrote %s", path.c_str());
}

}  // namespace esphome::preview_display
