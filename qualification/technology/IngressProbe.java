// Audit-only streaming ingress prototype. Not a qualification validator.
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.StreamReadFeature;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class IngressProbe {
    private static final long MAX_TIME = (1L << 53) - 1000;
    private static final JsonFactory FACTORY = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .streamReadConstraints(StreamReadConstraints.builder()
            .maxNestingDepth(8).maxNumberLength(17).maxStringLength(65536).build())
        .build();

    static byte[] admitted(byte[] bytes) throws Exception {
        if (bytes.length > 65536) throw new IllegalArgumentException();
        String text = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes)).toString();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (JsonParser parser = FACTORY.createParser(text);
             JsonGenerator generator = FACTORY.createGenerator(output)) {
            int depth = 0;
            int roots = 0;
            JsonToken token;
            while ((token = parser.nextToken()) != null) {
                if (depth == 0 && (token.isScalarValue() || token.isStructStart())) roots++;
                if (token.isStructStart()) depth++;
                if (token.isStructEnd()) depth--;
                if (roots > 1 || token == JsonToken.VALUE_NUMBER_FLOAT) {
                    throw new IllegalArgumentException();
                }
                if (token == JsonToken.VALUE_NUMBER_INT) {
                    String spelling = parser.getText();
                    long value = parser.getLongValue();
                    if (spelling.length() > 17 || value < -MAX_TIME || value > MAX_TIME) {
                        throw new IllegalArgumentException();
                    }
                }
                generator.copyCurrentEvent(parser);
            }
            if (roots != 1 || depth != 0) throw new IllegalArgumentException();
        }
        return output.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        // Bounded trusted test transport, not the production evidence interface.
        byte[] input = System.in.readNBytes(8 * 1024 * 1024 + 1);
        if (input.length > 8 * 1024 * 1024) throw new IllegalArgumentException();
        // Count before splitting: blank requests still consume the row budget.
        // One terminal LF ends a row; it does not start an extra empty request.
        int count = input.length > 0 && input[input.length - 1] != '\n' ? 1 : 0;
        for (byte value : input) {
            if (value == '\n') count++;
            if (count > 256) throw new IllegalArgumentException();
        }
        String[] rows = new String(input, StandardCharsets.US_ASCII).split("\n", -1);
        for (int index = 0; index < count; index++) {
            String row = rows[index];
            String response;
            try {
                byte[] document = admitted(HexFormat.of().parseHex(row));
                response = "{\"accepted\":true,\"document\":"
                    + new String(document, StandardCharsets.UTF_8) + "}\n";
            } catch (Exception rejected) {
                response = "{\"accepted\":false}\n";
            }
            // Byte writes avoid the default stdout charset. PrintStream stores
            // I/O failures internally; checkError flushes and observes that state.
            byte[] encoded = response.getBytes(StandardCharsets.UTF_8);
            System.out.write(encoded, 0, encoded.length);
            if (System.out.checkError()) {
                // Delivery failure must not become an input rejection response.
                throw new IOException("probe_output_unavailable");
            }
        }
    }
}
