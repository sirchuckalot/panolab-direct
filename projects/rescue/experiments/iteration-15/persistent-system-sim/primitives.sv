`timescale 1ns/1ps

module BUFG(input I, output O);
    assign O = I;
endmodule

module FDCE #(parameter INIT = 1'b0)(input C, CE, CLR, D, output reg Q = INIT);
    always @(posedge C or posedge CLR)
        if (CLR) Q <= 0;
        else if (CE) Q <= D;
endmodule

module FDPE #(parameter INIT = 1'b0)(input C, CE, PRE, D, output reg Q = INIT);
    always @(posedge C or posedge PRE)
        if (PRE) Q <= 1;
        else if (CE) Q <= D;
endmodule

// Only the staged design's complementary clocks, C0 alignment, and async
// controls are modeled. C1 emits the D1 value captured at C0.
module ODDR2 #(
    parameter DDR_ALIGNMENT = "C0", INIT = 1'b0, SRTYPE = "ASYNC"
)(input C0, C1, CE, D0, D1, R, S, output reg Q = INIT);
    reg d1_at_c0 = INIT;
    always @(posedge C0 or posedge R or posedge S)
        if (R) d1_at_c0 <= 0;
        else if (S) d1_at_c0 <= 1;
        else if (CE) d1_at_c0 <= D1;
    always @(posedge C0 or posedge C1 or posedge R or posedge S)
        if (R) Q <= 0;
        else if (S) Q <= 1;
        else if (CE) Q <= C0 ? D0 : d1_at_c0;
endmodule

module IDDR2 #(
    parameter DDR_ALIGNMENT = "C0", INIT_Q0 = 1'b0, INIT_Q1 = 1'b0,
    SRTYPE = "ASYNC"
)(input C0, C1, CE, D, R, S, output reg Q0 = INIT_Q0, Q1 = INIT_Q1);
    reg d_at_c1 = INIT_Q1;
    always @(posedge C1 or posedge R or posedge S)
        if (R) d_at_c1 <= 0;
        else if (S) d_at_c1 <= 1;
        else if (CE) d_at_c1 <= D;
    always @(posedge C0 or posedge R or posedge S)
        if (R) {Q0, Q1} <= 2'b00;
        else if (S) {Q0, Q1} <= 2'b11;
        else if (CE) {Q0, Q1} <= {D, d_at_c1};
endmodule

module IOBUF(input I, T, output O, inout IO);
    assign IO = T ? 1'bz : I;
    assign O = IO;
endmodule

// Ideal oscillator gated by reset. Lock asserts after eight input edges.
// Feedback, phase, jitter and loss of the input clock are outside this model.
module PLL_ADV #(
    parameter BANDWIDTH = "OPTIMIZED",
    parameter integer CLKFBOUT_MULT = 8,
    parameter real CLKFBOUT_PHASE = 0.0, CLKIN1_PERIOD = 8.0, CLKIN2_PERIOD = 0.0,
    parameter integer CLKOUT0_DIVIDE = 20,
    parameter real CLKOUT0_DUTY_CYCLE = 0.5, CLKOUT0_PHASE = 0.0,
    parameter CLK_FEEDBACK = "CLKFBOUT", COMPENSATION = "INTERNAL",
    parameter integer DIVCLK_DIVIDE = 1,
    parameter real REF_JITTER = 0.01,
    parameter SIM_DEVICE = "SPARTAN6"
)(input CLKFBIN, CLKIN1, CLKINSEL, RST,
  output CLKFBOUT, output reg CLKOUT0 = 0, LOCKED = 0);
    localparam real HALF_PERIOD =
        CLKIN1_PERIOD * DIVCLK_DIVIDE * CLKOUT0_DIVIDE / CLKFBOUT_MULT / 2.0;
    integer edges = 0;
    assign CLKFBOUT = CLKIN1;
    always #(HALF_PERIOD) CLKOUT0 = RST ? 1'b0 : ~CLKOUT0;
    always @(posedge CLKIN1 or posedge RST)
        if (RST) begin
            edges <= 0;
            LOCKED <= 0;
        end else if (!LOCKED) begin
            edges <= edges + 1;
            LOCKED <= edges == 7;
        end
endmodule
