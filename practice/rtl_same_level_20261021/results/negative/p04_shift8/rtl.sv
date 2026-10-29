module TopModule (
    input wire clk, reset, load, enable, serial_in,
    input wire [7:0] data,
    output reg [7:0] q
);
    always @(posedge clk) begin
        if (reset)
            q <= 8'h00;
        else if (load)
            q <= data;
        else if (enable)
            q <= {serial_in, q[7:1]};
    end
endmodule
