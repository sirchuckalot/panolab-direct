`timescale 1ns/1ps
module spartan6_icap #(
    parameter TARGET = -1,
    parameter FALLBACK = -1,
    parameter READ_OPCODE = -1
) (
    input wire clk,
    input wire reset,
    input wire arm,
    input wire start,
    output wire ready,
    output reg active,
    output reg done
);
    localparam [23:0] TARGET_ADDR = TARGET;
    localparam [23:0] FALLBACK_ADDR = FALLBACK;
    localparam [7:0] OPCODE = READ_OPCODE;

    generate
        if ((^TARGET === 1'bx) || TARGET < 0 || TARGET > 24'hffffff ||
            (^FALLBACK === 1'bx) || FALLBACK < 0 || FALLBACK > 24'hffffff ||
            (^READ_OPCODE === 1'bx) || READ_OPCODE < 0 || READ_OPCODE > 8'hff) begin : invalid_parameters
            ICAP_requires_explicit_24_bit_addresses_and_8_bit_opcode invalid();
        end
    endgenerate

    reg start_low_seen;
    reg [3:0] word_index;
    reg [15:0] word;

    assign ready = !reset && arm && start_low_seen && !active && !done;

    always @(posedge clk) begin
        if (reset) begin
            start_low_seen <= 1'b0;
            active <= 1'b0;
            done <= 1'b0;
            word_index <= 4'd0;
        end else if (active) begin
            if (word_index == 4'd13) begin
                active <= 1'b0;
                done <= 1'b1;
            end else begin
                word_index <= word_index + 4'd1;
            end
        end else if (!done) begin
            if (!arm)
                start_low_seen <= 1'b0;
            else if (!start)
                start_low_seen <= 1'b1;
            else if (ready)
                active <= 1'b1;
        end
    end

    always @* begin
        case (word_index)
            4'd0:  word = 16'hffff;
            4'd1:  word = 16'haa99;
            4'd2:  word = 16'h5566;
            4'd3:  word = 16'h3261;
            4'd4:  word = TARGET_ADDR[15:0];
            4'd5:  word = 16'h3281;
            4'd6:  word = {OPCODE, TARGET_ADDR[23:16]};
            4'd7:  word = 16'h32a1;
            4'd8:  word = FALLBACK_ADDR[15:0];
            4'd9:  word = 16'h32c1;
            4'd10: word = {OPCODE, FALLBACK_ADDR[23:16]};
            4'd11: word = 16'h30a1;
            4'd12: word = 16'h000e;
            4'd13: word = 16'h2000;
            default: word = 16'hffff;
        endcase
    end

    wire [15:0] icap_word;
    genvar bit_index;
    generate
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin : selectmap
            assign icap_word[bit_index] = word[7-bit_index];
            assign icap_word[8+bit_index] = word[15-bit_index];
        end
    endgenerate

    ICAP_SPARTAN6 icap (
        .CLK(clk),
        .CE(reset || !active),
        .WRITE(1'b0),
        .I(icap_word),
        .O(),
        .BUSY()
    );
endmodule
