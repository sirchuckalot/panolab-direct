`timescale 1ns/1ps

module tb;
    reg clk125 = 0;
    reg rst_n = 0;
    reg user_btn_n;
    wire flash_clk, flash_cs_n, flash_mosi, flash_miso;
    wire eth_mdio;
    integer duration_ms = 100;
    integer uart_bytes = 0;
    integer jedec_commands = 0;

    always #4 clk125 = ~clk125;
    assign eth_mdio = 1'bz;

    pano_logic_g2 dut (
        .clk125(clk125), .rst_n(rst_n), .user_btn_n(user_btn_n),
        .serial_rx(1'b1), .serial_tx(),
        .spiflash_clk(flash_clk), .spiflash_cs_n(flash_cs_n),
        .spiflash_miso(flash_miso), .spiflash_mosi(flash_mosi),
        .eth_clocks_rx(clk125), .eth_clocks_tx(clk125), .eth_clocks_gtx(),
        .eth_col(1'b0), .eth_crs(1'b0), .eth_int_n(1'b1),
        .eth_mdc(), .eth_mdio(eth_mdio), .eth_rst_n(),
        .eth_rx_data(8'b0), .eth_rx_dv(1'b0), .eth_rx_er(1'b0),
        .eth_tx_data(), .eth_tx_en(), .eth_tx_er()
    );

    // Mode 0. Capture MOSI on rising SCK and update MISO on falling SCK.
    // Return a synthetic EF 40 18 JEDEC ID and ones for all other reads.
    localparam [23:0] JEDEC_ID = 24'hef4018;
    reg [7:0] flash_command = 0;
    integer flash_bits = 0;
    reg miso_bit = 1;
    reg blank_flash;
    assign flash_miso = blank_flash || flash_cs_n || miso_bit;

    always @(posedge flash_clk or posedge flash_cs_n)
        if (flash_cs_n) begin
            flash_bits <= 0;
            flash_command <= 0;
        end else begin
            if (flash_bits < 8) begin
                flash_command <= {flash_command[6:0], flash_mosi};
                if (flash_bits == 7 && {flash_command[6:0], flash_mosi} == 8'h9f)
                    jedec_commands <= jedec_commands + 1;
            end
            flash_bits <= flash_bits + 1;
        end

    always @(negedge flash_clk or posedge flash_cs_n)
        if (flash_cs_n || flash_command != 8'h9f || flash_bits < 8 || flash_bits >= 32)
            miso_bit <= 1;
        else
            miso_bit <= JEDEC_ID[31 - flash_bits];

    always @(posedge dut.sys_clk)
        if (!dut.sys_rst && dut.rescuesoc_uart_core_tx_fifo_wrport_we) begin
            $write("%c", dut.rescuesoc_uart_core_tx_fifo_wrport_dat_w[7:0]);
            uart_bytes <= uart_bytes + 1;
        end

    initial begin
        user_btn_n = !$test$plusargs("button");
        blank_flash = $test$plusargs("blank_flash");
        if ($value$plusargs("ms=%d", duration_ms) && duration_ms <= 0)
            $fatal(1, "+ms must be positive");
        #200 rst_n = 1;
        #(duration_ms * 1ms);
        $display("\n[sim] UART bytes=%0d JEDEC commands=%0d sys_rst=%b",
                 uart_bytes, jedec_commands, dut.sys_rst);
        if (uart_bytes == 0) $fatal(1, "No UART bytes");
        $finish;
    end
endmodule
