const amountPattern = /^(?:\d+|\d{1,3}(?:\.\d{3})+)$/;
const maxCapital = 10_000_000_000_000_000_000n;
const group = new Intl.NumberFormat('vi-VN');

export function CapitalInput({ value, onChange, attempted = false }: { value: string; attempted?: boolean; onChange: (value: string) => void }) {
  const validAmount = amountPattern.test(value);
  const digits = value.replaceAll('.', '');
  const error = attempted && !value ? 'Nhập vốn kế hoạch để tiếp tục.' : value && (!validAmount || digits.length > 20 || BigInt(digits) < 1n || BigInt(digits) > maxCapital)
    ? 'Nhập số nguyên từ 1 đến 10.000.000.000.000.000.000 VND.' : '';

  function edit(input: HTMLInputElement, regroup: boolean, backwards = false) {
    const text = input.value;
    const raw = text.replaceAll('.', '');
    // After a mid-number edit the old separators may be in the wrong positions.
    if (raw.length > 20 || !(amountPattern.test(text) || (regroup && /^[\d.]*$/.test(text)))) {
      onChange(text);
      return;
    }

    const formatted = raw ? group.format(BigInt(raw)) : '';
    const caret = input.selectionStart ?? text.length;
    const remaining = text.slice(caret).replace(/\D/g, '').length;
    let position = formatted.length;
    for (let i = 0; i < remaining && position > 0; position--) {
      if (formatted[position - 1] !== '.') i++;
    }
    if (backwards && formatted[position - 1] === '.') position--;
    input.value = formatted;
    input.setSelectionRange(position, position);
    onChange(formatted);
  }

  return <label><span id="capital-label">Vốn kế hoạch<span className="sr-only"> (VND)</span></span>
    <span className="capital-field">
      <input name="capital" type="text" inputMode="numeric" required aria-labelledby="capital-label" placeholder="0"
        value={value} onChange={event => {
          const change = event.nativeEvent as InputEvent;
          const regroup = validAmount && (change.inputType?.startsWith('delete') || /^\d+$/.test(change.data ?? ''));
          edit(event.currentTarget, regroup, change.inputType === 'deleteContentBackward');
        }}
        onPaste={event => {
          const amount = event.clipboardData.getData('text').trim().replace(/\s*(?:₫|đ|VND)$/i, '');
          if (!amountPattern.test(amount)) return;
          event.preventDefault();
          const input = event.currentTarget;
          input.setRangeText(amount.replaceAll('.', ''), input.selectionStart ?? 0, input.selectionEnd ?? 0, 'end');
          edit(input, true);
        }}
        ref={input => { input?.setCustomValidity(error); }}
        aria-invalid={error ? true : undefined} aria-describedby={error ? 'capital-error' : undefined}/>
      <span aria-hidden="true">VND</span>
    </span>
    {error && <small id="capital-error" className="field-error">{error}</small>}
  </label>;
}
