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
            q <= {q[6:0], serial_in};
    end
endmodule
