import { CHARSET, SCRAMBLE_COLORS, FLIP_DURATION } from './constants.js';

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

    setTimeout(() => {
      this.el.classList.add('scrambling');
      let scrambleCount = 0;
      const maxScrambles = 10 + Math.floor(Math.random() * 4);
      const scrambleInterval = 70;

      this._scrambleTimer = setInterval(() => {
        // Random character
        const randChar = CHARSET[Math.floor(Math.random() * CHARSET.length)];
        this.frontSpan.textContent = randChar === ' ' ? '' : randChar;

        // Cycle background color
        const color = SCRAMBLE_COLORS[scrambleCount % SCRAMBLE_COLORS.length];
        this.frontEl.style.backgroundColor = color;

        // Briefly change text color for contrast on light backgrounds
        if (color === '#FFFFFF' || color === '#FFCC00') {
          this.frontSpan.style.color = '#111';
        } else {
          this.frontSpan.style.color = '';
        }

        scrambleCount++;

        if (scrambleCount >= maxScrambles) {
          clearInterval(this._scrambleTimer);
          this._scrambleTimer = null;

          // Reset temporary scramble colors before applying the final style.
          this.frontEl.style.backgroundColor = '';
          this.frontSpan.style.color = '#FFFFFF';

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
