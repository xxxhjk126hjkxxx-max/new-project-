/* Shared by the on-site app and the standalone student HTML. */
const AttendanceCode = (() => {
  const alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
  const pattern = /^[2-9A-HJ-NP-Z]{16}$/;
  const prefix = 'IUA1:';
  return Object.freeze({
    create() {
      return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => alphabet[byte & 31]).join('');
    },
    normalize(input) {
      const code = input.toUpperCase().replace(/[\s-]/g, '');
      return pattern.test(code) ? code : null;
    },
    format(code) { return code.match(/.{4}/g).join('-'); },
    encode(code) { return prefix + code; },
    decode(payload) {
      if (!payload.startsWith(prefix)) return null;
      const code = payload.slice(prefix.length);
      return pattern.test(code) ? code : null;
    },
  });
})();
