import { FLIP_DURATION } from './constants.js';

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const DIGITS = '0123456789';

export class Tile {
  constructor(row, col) {
    this.row = row;
    this.col = col;
    this.currentChar = ' ';
    this.isAnimating = false;
    this._scrambleTimer = null;

    // Build DOM
    this.el = document.createElement('div');
    this.el.className = 'tile';

    this.innerEl = document.createElement('div');
    this.innerEl.className = 'tile-inner';

    this.frontEl = document.createElement('div');
    this.frontEl.className = 'tile-front';
    this.frontSpan = document.createElement('span');
    this.frontEl.appendChild(this.frontSpan);

    this.backEl = document.createElement('div');
    this.backEl.className = 'tile-back';
    this.backSpan = document.createElement('span');
    this.backEl.appendChild(this.backSpan);

    this.innerEl.appendChild(this.frontEl);
    this.innerEl.appendChild(this.backEl);
    this.el.appendChild(this.innerEl);
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

  applyColorSpec(colorSpec) {
    const { fg, bg } = this.normalizeColorSpec(colorSpec);
    this.frontSpan.style.color = fg;
    this.frontEl.style.backgroundColor = bg;
  }

  setChar(char, colorSpec) {
    this.currentChar = char;
    this.frontSpan.textContent = char === ' ' ? '' : char;
    this.backSpan.textContent = '';
    this.applyColorSpec(colorSpec);
  }

  scrambleTo(targetChar, delay, settleColor) {
    if (targetChar === this.currentChar && !settleColor) return;

    // Cancel any in-progress animation
    if (this._scrambleTimer) {
      clearInterval(this._scrambleTimer);
      this._scrambleTimer = null;
    }
    this.isAnimating = true;

    // Determine which character pool to cycle through based on the target
    let pool;
    if (LETTERS.includes(targetChar)) {
      pool = LETTERS;
    } else if (DIGITS.includes(targetChar)) {
      pool = DIGITS;
    } else {
      pool = null; // spaces/punctuation — no cycling
    }

    // Apply the target color during the entire animation
    const { fg: settleFg, bg: settleBg } = this.normalizeColorSpec(settleColor);

    setTimeout(() => {
      // If no pool (space/punctuation), just set immediately with a flip
      if (!pool) {
        this.frontSpan.textContent = targetChar === ' ' ? '' : targetChar;
        this.applyColorSpec(settleColor);
        this.innerEl.style.transition = `transform ${FLIP_DURATION}ms ease-in-out`;
        this.innerEl.style.transform = 'perspective(400px) rotateX(-8deg)';
        setTimeout(() => {
          this.innerEl.style.transform = '';
          setTimeout(() => {
            this.innerEl.style.transition = '';
            this.currentChar = targetChar;
            this.isAnimating = false;
          }, FLIP_DURATION);
        }, FLIP_DURATION / 2);
        return;
      }

      this.el.classList.add('scrambling');
      let scrambleCount = 0;
      const maxScrambles = 10 + Math.floor(Math.random() * 4);
      const scrambleInterval = 70;

      // Apply target color immediately
      this.frontEl.style.backgroundColor = settleBg || '';
      this.frontSpan.style.color = settleFg;

      this._scrambleTimer = setInterval(() => {
        // Cycle through matching character type only
        const randChar = pool[Math.floor(Math.random() * pool.length)];
        this.frontSpan.textContent = randChar;

        scrambleCount++;

        if (scrambleCount >= maxScrambles) {
          clearInterval(this._scrambleTimer);
          this._scrambleTimer = null;

          // Set the final character
          this.frontSpan.textContent = targetChar === ' ' ? '' : targetChar;
          this.applyColorSpec(settleColor);

          // Quick flash effect: brief scale transform
          this.innerEl.style.transition = `transform ${FLIP_DURATION}ms ease-in-out`;
          this.innerEl.style.transform = 'perspective(400px) rotateX(-8deg)';

          setTimeout(() => {
            this.innerEl.style.transform = '';
            setTimeout(() => {
              this.innerEl.style.transition = '';
              this.el.classList.remove('scrambling');
              this.currentChar = targetChar;
              this.isAnimating = false;
            }, FLIP_DURATION);
          }, FLIP_DURATION / 2);
        }
      }, scrambleInterval);
    }, delay);
  }
}
