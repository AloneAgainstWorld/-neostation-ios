/// Utility functions for processing and decoding HTML content.
class HtmlUtils {
  /// Decodes a broad range of HTML entities into their corresponding Unicode characters.
  ///
  /// Examples:
  /// - `&quot;` becomes `"`
  /// - `&#39;` becomes `'`
  /// - `&amp;` becomes `&`
  ///
  /// Supports named entities, decimal codes (`&#123;`), and hexadecimal codes (`&#xABC;`).
  static String decodeHtmlEntities(String text) {
    if (text.isEmpty) return text;

    final entities = {
      '&quot;': '"',
      '&#34;': '"',
      '&apos;': "'",
      '&#39;': "'",
      '&amp;': '&',
      '&#38;': '&',
      '&lt;': '<',
      '&#60;': '<',
      '&gt;': '>',
      '&#62;': '>',
      '&nbsp;': ' ',
      '&#160;': ' ',
      '&iexcl;': '¡',
      '&#161;': '¡',
      '&cent;': '¢',
      '&#162;': '¢',
      '&pound;': '£',
      '&#163;': '£',
      '&euro;': '€',
      '&#8364;': '€',
      '&copy;': '©',
      '&#169;': '©',
      '&reg;': '®',
      '&#174;': '®',
      // Accented vowels (Spanish/Latin)
      '&aacute;': 'á',
      '&#225;': 'á',
      '&eacute;': 'é',
      '&#233;': 'é',
      '&iacute;': 'í',
      '&#237;': 'í',
      '&oacute;': 'ó',
      '&#243;': 'ó',
      '&uacute;': 'ú',
      '&#250;': 'ú',
      '&Aacute;': 'Á',
      '&#193;': 'Á',
      '&Eacute;': 'É',
      '&#201;': 'É',
      '&Iacute;': 'Í',
      '&#205;': 'Í',
      '&Oacute;': 'Ó',
      '&#211;': 'Ó',
      '&Uacute;': 'Ú',
      '&#218;': 'Ú',
      '&ntilde;': 'ñ',
      '&#241;': 'ñ',
      '&Ntilde;': 'Ñ',
      '&#209;': 'Ñ',
      // Accented vowels (French/European)
      '&agrave;': 'à',
      '&#224;': 'à',
      '&egrave;': 'è',
      '&#232;': 'è',
      '&ugrave;': 'ù',
      '&#249;': 'ù',
      '&acirc;': 'â',
      '&#226;': 'â',
      '&ecirc;': 'ê',
      '&#234;': 'ê',
      '&icirc;': 'î',
      '&#238;': 'î',
      '&ocirc;': 'ô',
      '&#244;': 'ô',
      '&ucirc;': 'û',
      '&#251;': 'û',
      '&ccedil;': 'ç',
      '&#231;': 'ç',
      '&Ccedil;': 'Ç',
      '&#199;': 'Ç',
      // Umlaut / Dieresis vowels
      '&auml;': 'ä',
      '&#228;': 'ä',
      '&euml;': 'ë',
      '&#235;': 'ë',
      '&iuml;': 'ï',
      '&#239;': 'ï',
      '&ouml;': 'ö',
      '&#246;': 'ö',
      '&uuml;': 'ü',
      '&#252;': 'ü',
      '&Auml;': 'Ä',
      '&#196;': 'Ä',
      '&Euml;': 'Ë',
      '&#203;': 'Ë',
      '&Iuml;': 'Ï',
      '&#207;': 'Ï',
      '&Ouml;': 'Ö',
      '&#214;': 'Ö',
      '&Uuml;': 'Ü',
      '&#220;': 'Ü',
    };

    String decoded = text;

    // Replace named and fixed numeric entities.
    entities.forEach((entity, char) {
      decoded = decoded.replaceAll(entity, char);
    });

    // Handle generic decimal entities (e.g., &#1234;).
    final decimalPattern = RegExp(r'&#(\d+);');
    decoded = decoded.replaceAllMapped(decimalPattern, (match) {
      try {
        final code = int.parse(match.group(1)!);
        return String.fromCharCode(code);
      } catch (e) {
        return match.group(0)!;
      }
    });

    // Handle generic hexadecimal entities (e.g., &#xABC;).
    final hexPattern = RegExp(r'&#x([0-9A-Fa-f]+);');
    decoded = decoded.replaceAllMapped(hexPattern, (match) {
      try {
        final code = int.parse(match.group(1)!, radix: 16);
        return String.fromCharCode(code);
      } catch (e) {
        return match.group(0)!;
      }
    });

    return decoded;
  }
}
