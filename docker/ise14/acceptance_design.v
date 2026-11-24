// Generic Spartan-6 ISE toolchain acceptance fixture.
// Deliberately UNCONSTRAINED: NOT a Pano G2 pinout or load-ready bitstream.
module panolab_ise_acceptance(
    input wire clk,
    input wire reset_n,
    output wire led
);
    reg [23:0] counter;
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n)
            counter <= 24'd0;
        else
            counter <= counter + 24'd1;
    end
    assign led = counter[22];
endmodule
