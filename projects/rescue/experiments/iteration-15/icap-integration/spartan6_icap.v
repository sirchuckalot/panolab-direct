`timescale 1ns/1ps

// Simulation-only transmitter. select_b is latched by the interlock.
module spartan6_icap (
    input wire clk,
    input wire reset,
    input wire launch,
    input wire select_b,
    output reg active,
    output reg done
);
    localparam [23:0] APP_A_ADDR = 24'h12_3456;
    localparam [23:0] APP_B_ADDR = 24'h65_4321;
    localparam [23:0] FALLBACK_ADDR = 24'h00_0000;
    localparam [7:0] OPCODE = 8'h03;

    generate
        if (APP_A_ADDR == APP_B_ADDR || APP_A_ADDR == FALLBACK_ADDR ||
            APP_B_ADDR == FALLBACK_ADDR) begin : overlapping_addresses
            ICAP_requires_distinct_APP_and_Rescue_addresses invalid();
        end
    endgenerate

    wire [23:0] app_addr = select_b ? APP_B_ADDR : APP_A_ADDR;
    reg [3:0] word_index;
    reg [15:0] word;

    always @(posedge clk) begin
        if (reset) begin
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
        end else if (launch && !done) begin
            active <= 1'b1;
        end
    end

    always @* begin
        case (word_index)
            4'd0:  word = 16'hffff;
            4'd1:  word = 16'haa99;
            4'd2:  word = 16'h5566;
            4'd3:  word = 16'h3261;
            4'd4:  word = app_addr[15:0];
            4'd5:  word = 16'h3281;
            4'd6:  word = {OPCODE, app_addr[23:16]};
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
