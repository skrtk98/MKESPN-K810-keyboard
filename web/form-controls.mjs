// Shared official DADS structures for static forms and generated macro fields.
export function enhanceControls(root = document) {
    for (const select of root.querySelectorAll('select.dads-select__select')) {
        if (select.closest('.dads-select__control')) continue;
        const wrapper = document.createElement('span');
        wrapper.className = 'dads-select';
        const control = document.createElement('span');
        control.className = 'dads-select__control';
        select.replaceWith(wrapper);
        wrapper.append(control);
        control.append(select);
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'dads-select__chevron');
        svg.setAttribute('width', '16');
        svg.setAttribute('height', '16');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS(svg.namespaceURI, 'path');
        path.setAttribute('d', 'M12 17L3 8L4 7L12 15L20 7L21 8L12 17Z');
        path.setAttribute('fill', 'currentColor');
        svg.append(path);
        control.append(svg);
    }
    for (const input of root.querySelectorAll('input:not([type=file]):not([type=checkbox]):not([type=color])')) {
        if (input.type === 'number') input.required = true;
        input.classList.add('dads-input-text__input');
        input.dataset.size = 'md';
        if (input.parentElement.classList.contains('dads-input-text')) continue;
        const wrapper = document.createElement('span');
        wrapper.className = 'dads-input-text';
        input.replaceWith(wrapper);
        wrapper.append(input);
    }
    for (const input of root.querySelectorAll('input[type=checkbox]')) {
        input.classList.add('dads-checkbox__input');
        if (input.closest('.dads-checkbox__checkbox')) continue;
        const label = input.closest('label');
        if (!label) continue;
        label.classList.add('dads-checkbox');
        label.dataset.size = 'sm';
        const box = document.createElement('span');
        box.className = 'dads-checkbox__checkbox';
        input.replaceWith(box);
        box.append(input);
        const text = document.createElement('span');
        text.className = 'dads-checkbox__label';
        for (const node of [...label.childNodes])
            if (node !== box) text.append(node);
        label.append(text);
    }
    for (const label of root.querySelectorAll('label:not(.dads-checkbox)')) {
        if (label.htmlFor) {
            label.classList.add('dads-form-control-label__label');
            continue;
        }
        if (!label.querySelector('input,select')) continue;
        label.classList.add('dads-form-control-label');
        label.dataset.size = 'sm';
        const text = [...label.childNodes].filter(node => node.nodeType === 3 && node.textContent.trim());
        if (text.length) {
            const name = document.createElement('span');
            name.className = 'dads-form-control-label__label';
            for (const node of text) name.append(node);
            label.prepend(name);
        }
    }
}
let nextError = 0;
export function clearFieldError(control) {
    const errorId = control.dataset.errorId;
    if (!errorId) return;
    document.getElementById(errorId)?.remove();
    control.removeAttribute('aria-invalid');
    const ids = (control.getAttribute('aria-describedby') ?? '').split(' ').filter(id => id && id !== errorId);
    if (ids.length) control.setAttribute('aria-describedby', ids.join(' '));
    else control.removeAttribute('aria-describedby');
    delete control.dataset.errorId;
}
export function fieldError(control, message) {
    clearFieldError(control);
    const error = document.createElement('p');
    error.id = `field-error-${++nextError}`;
    error.className = 'dads-input-text__error-text';
    error.setAttribute('role', 'alert');
    error.textContent = message;
    control.dataset.errorId = error.id;
    control.setAttribute('aria-invalid', 'true');
    control.setAttribute('aria-describedby', [control.getAttribute('aria-describedby'), error.id].filter(Boolean).join(' '));
    (control.closest('.dads-input-text,.dads-select') ?? control).after(error);
    control.focus();
}
export function validateFields(root) {
    for (const control of root.querySelectorAll('input[type=number]')) {
        if (!control.checkValidity()) {
            const task = control.closest('[data-light-task]');
            if (task?.hidden) {
                const picker = document.getElementById('light-view');
                picker.value = task.dataset.lightTask;
                picker.dispatchEvent(new Event('change'));
            }
            fieldError(control, control.validationMessage);
            return false;
        }
    }
    return true;
}
document.addEventListener('input', event => clearFieldError(event.target));
document.addEventListener('change', event => clearFieldError(event.target));