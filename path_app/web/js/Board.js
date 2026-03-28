import { Tile } from './Tile.js';
import { GRID_COLS, GRID_ROWS, STAGGER_DELAY, TOTAL_TRANSITION } from './constants.js';

const ALPHANUMERIC_GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
const TILE_FONT_FAMILY = "'Helvetica Neue', Helvetica, Arial, sans-serif";

export class Board {
  constructor(containerEl, soundEngine) {
    this.containerEl = containerEl;
    this.cols = GRID_COLS;
    this.rows = GRID_ROWS;
    this.soundEngine = soundEngine;
    this.isTransitioning = false;
    this.tiles = [];
    this.currentGrid = [];
    this.currentColors = [];
    this.charSizeCache = new Map();

    // Build board DOM
    this.boardEl = document.createElement('div');
    this.boardEl.className = 'board';
    this.boardEl.style.setProperty('--grid-cols', this.cols);
    this.boardEl.style.setProperty('--grid-rows', this.rows);

    // Tile grid
    this.gridEl = document.createElement('div');
    this.gridEl.className = 'tile-grid';

    for (let r = 0; r < this.rows; r++) {
      const row = [];
      const charRow = [];
      const colorRow = [];
      for (let c = 0; c < this.cols; c++) {
        const tile = new Tile(r, c);
        tile.setChar(' ');
        this.gridEl.appendChild(tile.el);
        row.push(tile);
        charRow.push(' ');
        colorRow.push('#FFFFFF');
      }
      this.tiles.push(row);
      this.currentGrid.push(charRow);
      this.currentColors.push(colorRow);
    }

    this.boardEl.appendChild(this.gridEl);
    containerEl.appendChild(this.boardEl);

    this.resizeObserver = new ResizeObserver(() => this.updateLayout());
    this.resizeObserver.observe(this.containerEl);
    this.updateLayout();
  }

  normalizeColorSpec(colorSpec) {
    if (typeof colorSpec === 'string' || !colorSpec) {
      return { fg: colorSpec || '#FFFFFF', bg: '' };
    }
    return {
      fg: colorSpec.fg || '#FFFFFF',
      bg: colorSpec.bg || ''
    };
  }

  colorSpecEquals(a, b) {
    const left = this.normalizeColorSpec(a);
    const right = this.normalizeColorSpec(b);
    return left.fg === right.fg && left.bg === right.bg;
  }

  getCharSizeForTile(tileSize) {
    if (this.charSizeCache.has(tileSize)) {
      return this.charSizeCache.get(tileSize);
    }

    const measureCanvas = document.createElement('canvas');
    const ctx = measureCanvas.getContext('2d');
    if (!ctx) {
      const fallbackSize = Math.floor(tileSize * 0.52);
      this.charSizeCache.set(tileSize, fallbackSize);
      return fallbackSize;
    }

    const maxGlyphWidth = Math.max(1, tileSize - 8);
    const maxGlyphHeight = Math.max(1, tileSize - 10);
    let low = 1;
    let high = tileSize;
    let best = Math.floor(tileSize * 0.52);

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      ctx.font = `700 ${mid}px ${TILE_FONT_FAMILY}`;

      let widestGlyph = 0;
      let tallestGlyph = 0;

      for (const glyph of ALPHANUMERIC_GLYPHS) {
        const metrics = ctx.measureText(glyph);
        const glyphWidth = (metrics.actualBoundingBoxLeft || 0) + (metrics.actualBoundingBoxRight || metrics.width);
        const glyphHeight = (metrics.actualBoundingBoxAscent || mid) + (metrics.actualBoundingBoxDescent || 0);
        widestGlyph = Math.max(widestGlyph, glyphWidth);
        tallestGlyph = Math.max(tallestGlyph, glyphHeight);
      }

      if (widestGlyph <= maxGlyphWidth && tallestGlyph <= maxGlyphHeight) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    this.charSizeCache.set(tileSize, best);
    return best;
  }

  updateLayout() {
    const rect = this.containerEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const styles = getComputedStyle(this.boardEl);
    const gap = parseFloat(styles.getPropertyValue('--tile-gap')) || 0;
    const paddingX = parseFloat(styles.getPropertyValue('--board-padding-x')) || 0;
    const paddingY = parseFloat(styles.getPropertyValue('--board-padding-y')) || 0;
    const availableWidth = Math.max(0, rect.width - (paddingX * 2));
    const availableHeight = Math.max(0, rect.height - (paddingY * 2));
    const tileWidth = (availableWidth - (gap * (this.cols - 1))) / this.cols;
    const tileHeight = (availableHeight - (gap * (this.rows - 1))) / this.rows;
    const tileSize = Math.max(1, Math.floor(Math.min(tileWidth, tileHeight)));
    const charSize = this.getCharSizeForTile(tileSize);

    this.boardEl.style.setProperty('--tile-size', `${tileSize}px`);
    this.boardEl.style.setProperty('--char-size', `${charSize}px`);
  }

  /**
   * Display rows of data with per-row or per-tile colors.
   * @param {Array<{text: string, colors: string|Object|Array<string|Object>}>} rowData
   *   Each entry has .text (padded to grid width) and .colors
   *   (a single color spec for the whole row, or an array of per-tile specs).
   */
  displayRows(rowData) {
    if (this.isTransitioning) return;
    this.isTransitioning = true;

    let hasChanges = false;

    for (let r = 0; r < this.rows; r++) {
      const entry = rowData[r] || { text: '', colors: '#FFFFFF' };
      const line = entry.text.toUpperCase();
      const padded = (line + ' '.repeat(this.cols)).substring(0, this.cols);
      const rowColors = Array.isArray(entry.colors)
        ? entry.colors
        : new Array(this.cols).fill(entry.colors || '#FFFFFF');

      for (let c = 0; c < this.cols; c++) {
        const newChar = padded[c];
        const newColor = rowColors[c] || '#FFFFFF';
        const oldChar = this.currentGrid[r][c];
        const oldColor = this.currentColors[r][c];

        if (newChar !== oldChar || !this.colorSpecEquals(newColor, oldColor)) {
          const delay = (r * this.cols + c) * STAGGER_DELAY;
          this.tiles[r][c].scrambleTo(newChar, delay, newColor);
          hasChanges = true;
        }
      }

      this.currentGrid[r] = padded.split('');
      this.currentColors[r] = rowColors.slice(0, this.cols);
    }

    if (hasChanges && this.soundEngine) {
      this.soundEngine.playTransition();
    }

    setTimeout(() => {
      this.isTransitioning = false;
    }, TOTAL_TRANSITION + 200);
  }

  /**
   * Update a single row without triggering transition lock.
   * Used for clock updates that shouldn't block data updates.
   */
  updateRow(rowIndex, text, color) {
    if (rowIndex < 0 || rowIndex >= this.rows) return;
    const line = text.toUpperCase();
    const padded = (line + ' '.repeat(this.cols)).substring(0, this.cols);
    const rowColor = color || '#FFFFFF';

    for (let c = 0; c < this.cols; c++) {
      const newChar = padded[c];
      const oldChar = this.currentGrid[rowIndex][c];
      const oldColor = this.currentColors[rowIndex][c];

      if (newChar !== oldChar || !this.colorSpecEquals(rowColor, oldColor)) {
        this.tiles[rowIndex][c].scrambleTo(newChar, 0, rowColor);
        this.currentGrid[rowIndex][c] = newChar;
        this.currentColors[rowIndex][c] = rowColor;
      }
    }
  }
}
