`timescale 1ns/1ps

module tb_icap_launch_interlock;
    reg clk = 0;
    always #50 clk = ~clk;

    reg reset, trusted_arm, start, select_b;
    reg durable_trial_valid, image_verified, spi_idle, spi_lock_grant;
    wire spi_lock_request, accepted, active, done;

    icap_launch_interlock dut (.*);

    reg [15:0] expected [0:13];
    integer words;
    integer slot;
    integer missing;
    reg allow_words = 0;

    // Observe the actual primitive pins on its sampling edge.
    always @(posedge clk) begin
        if (dut.transmitter.icap.CE === 1'b0) begin
            if (!allow_words || words >= 14)
                $fatal(1, "Unexpected ICAP write at word %0d", words);
            if (dut.transmitter.icap.WRITE !== 1'b0 ||
                dut.transmitter.icap.I !== expected[words])
                $fatal(1, "ICAP word %0d: got %h expected %h",
                       words, dut.transmitter.icap.I, expected[words]);
            if (spi_lock_request !== 1'b1 || accepted !== 1'b1)
                $fatal(1, "ICAP write without retained SPI request and acceptance");
            words = words + 1;
        end else if (dut.transmitter.icap.CE !== 1'b1) begin
            $fatal(1, "Unknown ICAP CE");
        end
    end

    task tick;
        begin
            @(posedge clk);
            @(negedge clk);
        end
    endtask

    task initialize;
        input initial_start;
        begin
            reset = 1;
            trusted_arm = 1;
            start = initial_start;
            select_b = 0;
            durable_trial_valid = 1;
            image_verified = 1;
            spi_idle = 1;
            spi_lock_grant = 0;
            words = 0;
            allow_words = 0;
            tick;
            if ({spi_lock_request, accepted, active, done} !== 4'b0000)
                $fatal(1, "Reset did not clear launch state");
            reset = 0;
        end
    endtask

    task expect_quiet;
        begin
            repeat (18) tick;
            if ({accepted, active, done} !== 3'b000 || words != 0)
                $fatal(1, "Launch occurred without a qualified start");
        end
    endtask

    initial begin
        // Fixed wire-order values, with bits reversed within each byte.
        expected[0]  = 16'hffff;
        expected[1]  = 16'h5599;
        expected[2]  = 16'haa66;
        expected[3]  = 16'h4c86;
        expected[5]  = 16'h4c81;
        expected[7]  = 16'h4c85;
        expected[8]  = 16'h0000;
        expected[9]  = 16'h4c83;
        expected[10] = 16'hc000;
        expected[11] = 16'h0c85;
        expected[12] = 16'h0070;
        expected[13] = 16'h0400;

        for (missing = 0; missing < 6; missing = missing + 1) begin
            initialize(0);
            tick;
            if (spi_lock_request !== 1'b1 || accepted !== 1'b0)
                $fatal(1, "SPI request must precede acceptance");
            spi_lock_grant = 1;
            case (missing)
                0: trusted_arm = 0;
                1: durable_trial_valid = 0;
                2: image_verified = 0;
                3: spi_idle = 0;
                4: spi_lock_grant = 0;
                5: select_b = 1'bx;
            endcase
            start = 1;
            expect_quiet;
            trusted_arm = 1;
            durable_trial_valid = 1;
            image_verified = 1;
            spi_idle = 1;
            spi_lock_grant = 1;
            select_b = 0;
            expect_quiet;
        end

        initialize(1);
        tick;
        spi_lock_grant = 1;
        expect_quiet;

        // Even an asserted grant cannot qualify an edge before the request.
        initialize(0);
        durable_trial_valid = 0;
        tick;
        durable_trial_valid = 1;
        spi_lock_grant = 1;
        start = 1;
        expect_quiet;

        for (slot = 0; slot < 2; slot = slot + 1) begin
            initialize(0);
            select_b = slot[0];
            expected[4] = slot ? 16'hc284 : 16'h2c6a;
            expected[6] = slot ? 16'hc0a6 : 16'hc048;
            tick;
            if (spi_lock_request !== 1'b1 || accepted !== 1'b0)
                $fatal(1, "SPI request must precede acceptance");
            spi_lock_grant = 1;
            start = 1;
            allow_words = 1;
            tick;
            if (accepted !== 1'b1)
                $fatal(1, "Qualified launch was not accepted");
            // Change the selection before the transmitter samples its launch.
            select_b = !select_b;
            trusted_arm = 0;
            durable_trial_valid = 0;
            image_verified = 0;
            repeat (18) tick;
            if (words != 14 || {accepted, active, done, spi_lock_request} !== 4'b1011)
                $fatal(1, "Incomplete packet or incorrect final launch state");

            allow_words = 0;
            trusted_arm = 1;
            durable_trial_valid = 1;
            image_verified = 1;
            start = 0;
            tick;
            start = 1;
            repeat (18) tick;
            if (words != 14 || {accepted, active, done, spi_lock_request} !== 4'b1011)
                $fatal(1, "Unexpected state after second start");
        end

        // Reset during transmission disables CE and consumes the held start.
        initialize(0);
        select_b = 1;
        tick;
        spi_lock_grant = 1;
        start = 1;
        allow_words = 1;
        wait (words == 5);
        @(negedge clk);
        reset = 1;
        allow_words = 0;
        tick;
        if ({spi_lock_request, accepted, active, done} !== 4'b0000)
            $fatal(1, "Reset during transmission did not clear interlock state");
        words = 0;
        reset = 0;
        expect_quiet;

        $display("PASS: APP A/B ICAP packets and launch interlock");
        $finish;
    end
endmodule
