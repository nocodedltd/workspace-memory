const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const revealElements = document.querySelectorAll('.reveal');

if (reducedMotion || !('IntersectionObserver' in window)) {
  revealElements.forEach((element) => element.classList.add('visible'));
} else {
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

  revealElements.forEach((element) => revealObserver.observe(element));
}

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const value = button.dataset.copy;
    if (!value) return;

    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = value;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.append(textArea);
      textArea.select();
      document.execCommand('copy');
      textArea.remove();
    }

    const label = button.querySelector('.copy-label');
    const originalLabel = label?.textContent;
    button.classList.add('copied');
    if (label) label.textContent = 'Copied';
    button.setAttribute('aria-label', 'Copied to clipboard');

    window.setTimeout(() => {
      button.classList.remove('copied');
      if (label && originalLabel) label.textContent = originalLabel;
      button.setAttribute('aria-label', 'Copy to clipboard');
    }, 1800);
  });
});

const timeline = document.querySelector('[data-timeline]');

if (timeline && !reducedMotion) {
  const updateTimeline = () => {
    const bounds = timeline.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const rawProgress = (viewportHeight - bounds.top) / (viewportHeight + bounds.height * 0.45);
    const progress = Math.max(0, Math.min(1, rawProgress));
    timeline.style.setProperty('--timeline-progress', `${progress * 86}%`);
  };

  updateTimeline();
  window.addEventListener('scroll', updateTimeline, { passive: true });
  window.addEventListener('resize', updateTimeline);
}

const typingCommand = document.querySelector('.typing-command');

if (typingCommand && !reducedMotion) {
  const fullText = typingCommand.textContent ?? '';

  const typeCommand = () => {
    let index = 0;
    typingCommand.textContent = '';
    const interval = window.setInterval(() => {
      typingCommand.textContent = fullText.slice(0, index + 1);
      index += 1;
      if (index >= fullText.length) window.clearInterval(interval);
    }, 42);
  };

  const terminalObserver = new IntersectionObserver((entries, observer) => {
    if (!entries.some((entry) => entry.isIntersecting)) return;
    typeCommand();
    observer.disconnect();
  }, { threshold: 0.35 });

  terminalObserver.observe(typingCommand);
}
