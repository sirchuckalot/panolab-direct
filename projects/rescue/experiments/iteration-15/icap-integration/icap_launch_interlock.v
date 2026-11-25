`timescale 1ns/1ps

module icap_launch_interlock (
    input wire clk,
    input wire reset,
    input wire trusted_arm,
    input wire start,
    input wire select_b,
    input wire durable_trial_valid,
    input wire image_verified,
    input wire spi_idle,
    input wire spi_lock_grant,
    output reg spi_lock_request,
    output reg accepted,
    output wire active,
    output wire done
);
    reg start_was_low;
    reg latched_select_b;

    wire eligible = (trusted_arm === 1'b1) &&
                    (durable_trial_valid === 1'b1) &&
                    (image_verified === 1'b1) &&
                    (spi_idle === 1'b1) &&
                    ((select_b === 1'b0) || (select_b === 1'b1));

    always @(posedge clk) begin
        if (reset) begin
            spi_lock_request <= 1'b0;
            accepted <= 1'b0;
            start_was_low <= 1'b0;
            latched_select_b <= 1'b0;
        end else if (!accepted) begin
            spi_lock_request <= eligible;
            start_was_low <= (trusted_arm === 1'b1) && (start === 1'b0);
            if (eligible && spi_lock_request && (spi_lock_grant === 1'b1) &&
                start_was_low && (start === 1'b1)) begin
                accepted <= 1'b1;
                latched_select_b <= select_b;
            end
        end
    end

    spartan6_icap transmitter (
        .clk(clk),
        .reset(reset),
        .launch(accepted),
        .select_b(latched_select_b),
        .active(active),
        .done(done)
    );
endmodule
