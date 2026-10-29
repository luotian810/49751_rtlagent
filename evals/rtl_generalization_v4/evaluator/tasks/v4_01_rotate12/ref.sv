module RefModule(input [11:0] word_i,input [3:0] distance_i,
 input turn_right_i,output reg [11:0] word_o);
 reg [3:0] k;
 always @* begin
   k=(distance_i>=12)?distance_i-12:distance_i;
   if(k==0) word_o=word_i;
   else if(turn_right_i) word_o=(word_i>>k)|(word_i<<(12-k));
   else word_o=(word_i<<k)|(word_i>>(12-k));
 end
endmodule
