/**
 * Bridge between PyQt6 backend and split-flap display.
 * Exposes global functions called from Python via runJavaScript().
 */
import { Board } from './Board.js';
import { SoundEngine } from './SoundEngine.js';
import { GRID_COLS } from './constants.js';

let board = null;
let soundEngine = null;
let clockInterval = null;
let headerStation = 'HOBOKEN PATH';

const STATION_LABELS = {
  HOB: 'HOBOKEN PATH',
  HOBOKEN: 'HOBOKEN PATH',
  CHR: 'CHRIS ST',
  'CHRISTOPHER STREET': 'CHRIS ST',
  JSQ: 'JOURNAL SQ',
  'JOURNAL SQUARE': 'JOURNAL SQ'
};

document.addEventListener('DOMContentLoaded', async () => {
  const container = document.getElementById('board-container');
  soundEngine = new SoundEngine();
  board = new Board(container, soundEngine);

  // Auto-initialize audio (no user gesture needed in QWebEngineView)
  await soundEngine.init();
  soundEngine.resume();

  // Start JS-side clock updates on the header row.
  updateClockRow();
  clockInterval = setInterval(updateClockRow, 1000);

  // Signal to Python that the page is ready.
  window._boardReady = true;
});

function formatHeaderClock(now = new Date()) {
  let hours = now.getHours();
  const mins = String(now.getMinutes()).padStart(2, '0');
  const ampm = hours >= 12 ? 'P' : 'A';
  hours = hours % 12 || 12;
  return String(hours) + ':' + mins + ampm;
}

function buildAlignedRow(left, right) {
  const normalizedRight = right.toUpperCase().trim();
  const maxLeftLength = Math.max(0, GRID_COLS - normalizedRight.length - 1);
  const normalizedLeft = left.toUpperCase().trim().slice(0, maxLeftLength);
  const gap = Math.max(1, GRID_COLS - normalizedLeft.length - normalizedRight.length);
  return (normalizedLeft + ' '.repeat(gap) + normalizedRight)
    .padEnd(GRID_COLS)
    .slice(0, GRID_COLS);
}

function buildHeaderText() {
  return buildAlignedRow(headerStation, formatHeaderClock());
}

function updateClockRow() {
  if (!board) return;
  board.updateRow(0, buildHeaderText(), '#FFFFFF');
}

function buildStatusRow(status, lastUpdated) {
  const STATUS_MAP = {
    LIVE:  { text: 'LIVE',  color: '#56CC9D' },
    DELAY: { text: 'DELAY', color: '#FF6B6B' },
    STALE: { text: 'STALE', color: '#E0A800' },
  };
  const entry = STATUS_MAP[status] || STATUS_MAP.STALE;
  const statusText = entry.text;
  const timeText = (lastUpdated || '--:--:-- --').toUpperCase();
  const rowText = buildAlignedRow(statusText, timeText);
  const statusColor = entry.color;
  const colors = new Array(GRID_COLS).fill('#9FB3C8');
  const statusStart = rowText.indexOf(statusText);

  if (statusStart >= 0) {
    for (let c = statusStart; c < statusStart + statusText.length; c++) {
      colors[c] = statusColor;
    }
  }

  return { rowText, colors };
}

/**
 * Called from Python when new train data arrives.
 * @param {Object} data - { rows: [{text, color}, ...] }
 */
window.updateBoard = function(data) {
  if (!board) return;

  const rows = data.rows || [];
  const rowData = [];

  for (let i = 0; i < 7; i++) {
    if (i === 0) {
      rowData.push({ text: buildHeaderText(), colors: '#FFFFFF' });
    } else if (i === 6) {
      rowData.push({
        text: board.currentGrid[6].join(''),
        colors: board.currentColors[6]
      });
    } else if (rows[i - 1]) {
      rowData.push({
        text: rows[i - 1].text || '',
        colors: rows[i - 1].color || '#FFFFFF'
      });
    } else {
      rowData.push({ text: '', colors: '#FFFFFF' });
    }
  }

  board.displayRows(rowData);
};

/**
 * Called from Python when status changes.
 * Updates the status row without changing the public bridge API.
 */
window.setStatus = function(status, lastUpdated) {
  if (!board) return;

  const { rowText, colors } = buildStatusRow(status, lastUpdated);

  board.updateRow(6, rowText, '#9FB3C8');
  const padded = (rowText.toUpperCase() + ' '.repeat(GRID_COLS)).substring(0, GRID_COLS);
  for (let c = 0; c < GRID_COLS; c++) {
    const ch = padded[c];
    const color = colors[c];
    board.tiles[6][c].setChar(ch, color);
    board.currentGrid[6][c] = ch;
    board.currentColors[6][c] = color;
  }
};

/**
 * Update the station name in the header.
 */
window.setStation = function(name) {
  const normalized = (name || '').toUpperCase().trim();
  headerStation = STATION_LABELS[normalized] || normalized.slice(0, 10);
  updateClockRow();
};
