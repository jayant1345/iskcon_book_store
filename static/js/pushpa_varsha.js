/**
 * ISKCON Book Store — Pushpa Varsha (Sacred Flower Shower)
 * Divine falling marigold, lotus, and jasmine petals over the Hero Carousel.
 * Lightweight, GPU-accelerated HTML5 Canvas with organic flutter and breeze.
 */

(function () {
  'use strict';

  function initPushpaVarsha() {
    const carousel = document.getElementById('heroCarousel');
    if (!carousel) return;

    // Check if canvas already exists
    let canvas = document.getElementById('pushpaVarshaCanvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'pushpaVarshaCanvas';
      canvas.setAttribute('aria-hidden', 'true');
      canvas.style.cssText = `
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 4;
      `;
      carousel.style.position = 'relative';
      carousel.appendChild(canvas);
    }

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let width = (canvas.width = carousel.offsetWidth);
    let height = (canvas.height = carousel.offsetHeight);

    function resize() {
      if (!carousel) return;
      width = canvas.width = carousel.offsetWidth;
      height = canvas.height = carousel.offsetHeight;
    }

    window.addEventListener('resize', resize, { passive: true });

    // Petal types inspired by Google Stitch Vedic aesthetic:
    // 0: Pink/Rose Sacred Lotus Petal
    // 1: Golden Saffron Marigold (Genda) Petal
    // 2: Pristine White Jasmine (Mogra) Blossom
    // 3: Sacred Parijata (Kalpavriksha) Star Blossom with Saffron Eye
    const TYPES = ['lotus', 'marigold', 'jasmine', 'parijata'];
    const MAX_PETALS = Math.min(46, Math.max(24, Math.floor(width / 30)));
    const petals = [];

    class Petal {
      constructor(initial = false) {
        this.reset(initial);
      }

      reset(initial = false) {
        this.type = TYPES[Math.floor(Math.random() * TYPES.length)];
        this.x = Math.random() * width;
        this.y = initial ? Math.random() * height : -30 - Math.random() * 40;
        this.scale = 0.55 + Math.random() * 0.65;
        this.vy = 0.85 + Math.random() * 1.35; // Graceful celestial floating speed
        this.sway = Math.random() * Math.PI * 2;
        this.swaySpeed = 0.015 + Math.random() * 0.025;
        this.swayWidth = 0.8 + Math.random() * 1.6;
        this.rotation = Math.random() * Math.PI * 2;
        this.vRot = (Math.random() - 0.5) * 0.025;
        this.tilt = Math.random() * Math.PI * 2;
        this.tiltSpeed = 0.02 + Math.random() * 0.035;
        this.opacity = 0.75 + Math.random() * 0.25;
      }

      update(windX = 0) {
        this.sway += this.swaySpeed;
        this.tilt += this.tiltSpeed;
        this.rotation += this.vRot;

        this.x += Math.sin(this.sway) * this.swayWidth + windX;
        this.y += this.vy;

        // Wrap around horizontally
        if (this.x < -40) this.x = width + 30;
        if (this.x > width + 40) this.x = -30;

        // Reset when falling below canvas
        if (this.y > height + 40) {
          this.reset(false);
        }
      }

      draw(c) {
        c.save();
        c.translate(this.x, this.y);
        c.rotate(this.rotation);
        // 3D perspective tumbling (scaleY based on tilt)
        const tiltScale = Math.cos(this.tilt);
        c.scale(this.scale, this.scale * tiltScale);
        c.globalAlpha = this.opacity;

        if (this.type === 'lotus') {
          // Delicate pink & saffron-tipped sacred lotus petal
          const grad = c.createLinearGradient(0, -18, 0, 18);
          grad.addColorStop(0, '#FB7185'); // Rose pink tip
          grad.addColorStop(0.45, '#FDA4AF');
          grad.addColorStop(0.9, '#FDE68A'); // Golden base
          grad.addColorStop(1, '#F59E0B');

          c.fillStyle = grad;
          c.beginPath();
          c.moveTo(0, -18);
          c.bezierCurveTo(11, -12, 12, 10, 0, 18);
          c.bezierCurveTo(-12, 10, -11, -12, 0, -18);
          c.closePath();
          c.fill();

          // Delicate petal vein highlight
          c.strokeStyle = 'rgba(255, 255, 255, 0.4)';
          c.lineWidth = 0.6;
          c.beginPath();
          c.moveTo(0, -14);
          c.lineTo(0, 14);
          c.stroke();
        } else if (this.type === 'marigold') {
          // Vibrant temple marigold (Genda) flame petal
          const grad = c.createLinearGradient(0, -14, 0, 14);
          grad.addColorStop(0, '#F59E0B'); // Deep rich gold
          grad.addColorStop(0.5, '#FBBF24'); // Luminous amber
          grad.addColorStop(1, '#EA580C'); // Saffron orange base

          c.fillStyle = grad;
          c.beginPath();
          c.moveTo(0, -15);
          c.bezierCurveTo(9, -9, 8, 8, 0, 15);
          c.bezierCurveTo(-8, 8, -9, -9, 0, -15);
          c.closePath();
          c.fill();

          // Soft highlight glow
          c.fillStyle = 'rgba(254, 243, 199, 0.4)';
          c.beginPath();
          c.ellipse(0, -4, 3, 7, 0, 0, Math.PI * 2);
          c.fill();
        } else if (this.type === 'jasmine') {
          // White Jasmine / Mogra sacred flower (5 rounded white petals)
          c.fillStyle = '#FFFFFF';
          c.shadowColor = 'rgba(254, 240, 138, 0.4)';
          c.shadowBlur = 5;

          for (let i = 0; i < 5; i++) {
            c.save();
            c.rotate((i * Math.PI * 2) / 5);
            c.beginPath();
            c.ellipse(0, -8, 4.5, 7.5, 0, 0, Math.PI * 2);
            c.fill();
            c.restore();
          }

          // Golden sacred flower core
          c.shadowBlur = 0;
          c.fillStyle = '#F59E0B';
          c.beginPath();
          c.arc(0, 0, 2.8, 0, Math.PI * 2);
          c.fill();
        } else if (this.type === 'parijata') {
          // Sacred Parijata (Krishna's celestial flower) — pristine white petals with glowing saffron stalk eye
          c.shadowColor = 'rgba(254, 240, 138, 0.5)';
          c.shadowBlur = 6;
          c.fillStyle = '#FFFFFF';

          for (let i = 0; i < 5; i++) {
            c.save();
            c.rotate((i * Math.PI * 2) / 5);
            c.beginPath();
            c.moveTo(0, -2);
            c.bezierCurveTo(3.5, -6, 4.5, -12, 0, -16);
            c.bezierCurveTo(-4.5, -12, -3.5, -6, 0, -2);
            c.closePath();
            c.fill();
            c.restore();
          }

          // Luminous saffron-orange central tube / eye
          c.shadowBlur = 4;
          c.shadowColor = '#F97316';
          const eyeGrad = c.createRadialGradient(0, 0, 0, 0, 0, 3.2);
          eyeGrad.addColorStop(0, '#EA580C');
          eyeGrad.addColorStop(0.7, '#F97316');
          eyeGrad.addColorStop(1, '#FDE047');
          c.fillStyle = eyeGrad;
          c.beginPath();
          c.arc(0, 0, 3.2, 0, Math.PI * 2);
          c.fill();
        }

        c.restore();
      }
    }

    // Divya Parag (Sacred Golden Pollen / Stardust Motes)
    const SPARKLE_COUNT = Math.min(22, Math.floor(width / 45));
    const sparkles = [];

    class DivyaParag {
      constructor(initial = false) {
        this.reset(initial);
      }

      reset(initial = false) {
        this.x = Math.random() * width;
        this.y = initial ? Math.random() * height : -10;
        this.size = 1.0 + Math.random() * 2.0;
        this.vy = 0.25 + Math.random() * 0.5;
        this.vx = (Math.random() - 0.5) * 0.3;
        this.phase = Math.random() * Math.PI * 2;
        this.phaseSpeed = 0.025 + Math.random() * 0.04;
        this.baseAlpha = 0.3 + Math.random() * 0.45;
      }

      update(wind) {
        this.phase += this.phaseSpeed;
        this.x += this.vx + wind * 0.35;
        this.y += this.vy;
        if (this.y > height + 10 || this.x < -10 || this.x > width + 10) {
          this.reset(false);
        }
      }

      draw(c) {
        const alpha = this.baseAlpha + Math.sin(this.phase) * 0.25;
        if (alpha <= 0) return;
        c.save();
        c.globalAlpha = Math.max(0.08, Math.min(0.9, alpha));
        c.fillStyle = '#FEF08A';
        c.shadowColor = '#F59E0B';
        c.shadowBlur = 5;
        c.beginPath();
        c.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        c.fill();
        c.restore();
      }
    }

    // Populate initial petals & sparkles
    for (let i = 0; i < MAX_PETALS; i++) {
      petals.push(new Petal(true));
    }
    for (let i = 0; i < SPARKLE_COUNT; i++) {
      sparkles.push(new DivyaParag(true));
    }

    // Interactive mouse wind reaction
    let windTarget = 0;
    let windCurrent = 0;

    carousel.addEventListener(
      'mousemove',
      (e) => {
        const rect = carousel.getBoundingClientRect();
        const relativeX = (e.clientX - rect.left) / rect.width - 0.5;
        windTarget = relativeX * 1.8;
      },
      { passive: true }
    );

    carousel.addEventListener(
      'mouseleave',
      () => {
        windTarget = 0;
      },
      { passive: true }
    );

    let isVisible = true;
    let animId = null;

    // Pause when off-screen to conserve GPU/CPU
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          isVisible = entries[0].isIntersecting;
          if (isVisible && !animId) {
            animId = requestAnimationFrame(render);
          }
        },
        { threshold: 0.1 }
      );
      observer.observe(carousel);
    }

    // Pause when browser tab inactive
    document.addEventListener('visibilitychange', () => {
      isVisible = !document.hidden;
      if (isVisible && !animId) {
        animId = requestAnimationFrame(render);
      }
    });

    function render() {
      if (!isVisible) {
        animId = null;
        return;
      }

      ctx.clearRect(0, 0, width, height);

      // Smooth wind interpolation
      windCurrent += (windTarget - windCurrent) * 0.04;

      // Draw subtle golden stardust behind petals
      for (let j = 0; j < sparkles.length; j++) {
        sparkles[j].update(windCurrent);
        sparkles[j].draw(ctx);
      }

      // Draw divine Pushpa Varsha blossoms and petals
      for (let i = 0; i < petals.length; i++) {
        petals[i].update(windCurrent);
        petals[i].draw(ctx);
      }

      animId = requestAnimationFrame(render);
    }

    animId = requestAnimationFrame(render);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPushpaVarsha);
  } else {
    initPushpaVarsha();
  }
})();
